"""Register W3 v16 Kaggle primal inputs and acceptance rules before execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "ramhachi888/cfd-opt-sdf-v16-genesis-state"
OUTPUT = ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09.json"
STATE = ROOT / "work/sdf_native_genesis_v16/sdf_design_state.npz"
STL = ROOT / "docs/evidence/assets/stage_v_v16_physical_profile_v2/v16_candidate_threshold_0p5.iso_surface.stl"
DOMAIN_STL = ROOT / "docs/evidence/assets/stage_v_v16_physical_profile_v2/geometry/design_domain.stl"
PROFILE = ROOT / "docs/evidence/assets/stage_v_v16_physical_profile_v2/project_matched_re_laminar_moving_ground_far_field_v2.yaml"
PROFILE_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_contract_manifest_v2_2026_09.json"
PROFILE_LINEAGE = ROOT / "docs/evidence/stage_v_v16_physical_profile_candidate_lineage_v2_2026_09.json"
GENESIS = ROOT / "docs/evidence/sdf_native_genesis_v16_2026_09.json"
W1_RESULT = ROOT / "docs/evidence/sdf_native_w1_grid_sdf_body_2026_09.json"
W2B_CRITERIA = ROOT / "docs/evidence/kaggle_w2b_criteria_2026_09_round5.json"
W2B_RESULT = ROOT / "docs/evidence/kaggle_w2b_round5_result_2026_09.json"
STAGE_V_SMALL_BOX = ROOT / "docs/evidence/stage_v_v16_physical_profile_qualification_v1_2026_09.json"
STAGE_V_EXPANDED = ROOT / "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json"
STAGE_V_DOMAIN_PAIR = ROOT / "docs/evidence/stage_v_v16_physical_profile_domain_convergence_result_v1_2026_09.json"
T4_PROJECT = ROOT / "julia/CFDSDFWaterLilyT4/Project.toml"
T4_MANIFEST = ROOT / "julia/CFDSDFWaterLilyT4/Manifest.toml"
RUNNER = ROOT / "infra/kaggle/kernel_w3/runner.py"
JOB = ROOT / "scripts/waterlily_w3_v16_primal_job.jl"
ADAPTER = ROOT / "julia/CFDSDFWaterLily/src/V16PhysicalProfile.jl"
PREPARER = ROOT / "scripts/prepare_kaggle_w3_dataset_2026_09.py"
SMOKE = ROOT / "scripts/w0b_t4_smoke.jl"
HOST_VERIFIER = ROOT / "scripts/verify_kaggle_w3_v16.py"
W3_TESTS = ROOT / "tests/test_kaggle_w3.py"
ADAPTER_TEST = ROOT / "julia/CFDSDFWaterLily/test/test_v16_physical_profile_adapter.jl"

SOURCE_INPUTS = {
    "kernel_runner": RUNNER,
    "job": JOB,
    "adapter": ADAPTER,
    "dataset_preparer": PREPARER,
    "host_verifier": HOST_VERIFIER,
    "kaggle_smoke": SMOKE,
    "project": T4_PROJECT,
    "manifest": T4_MANIFEST,
    "candidate_stl": STL,
    "design_domain_stl": DOMAIN_STL,
    "profile_spec": PROFILE,
    "profile_contract_manifest": PROFILE_MANIFEST,
    "profile_candidate_lineage": PROFILE_LINEAGE,
    "genesis_evidence": GENESIS,
    "w1_result": W1_RESULT,
    "w2b_criteria": W2B_CRITERIA,
    "w2b_result": W2B_RESULT,
    "stage_v_small_box_diagnostic": STAGE_V_SMALL_BOX,
    "stage_v_expanded_domain_pass": STAGE_V_EXPANDED,
    "stage_v_domain_pair_result": STAGE_V_DOMAIN_PAIR,
    "criteria_registrar": Path(__file__).resolve(),
    "python_tests": W3_TESTS,
    "adapter_test": ADAPTER_TEST,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def input_entry(path: Path, *, location: str = "source_repo") -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix() if location == "source_repo" else path.name,
        "sha256": sha256(path),
        "location": location,
    }


def criteria_output_path(criteria_round: int) -> Path:
    if criteria_round < 1:
        raise ValueError("W3 criteria round must be positive")
    if criteria_round == 1:
        return OUTPUT
    return OUTPUT.with_name(
        f"kaggle_w3_v16_primal_criteria_2026_09_round{criteria_round}.json"
    )


def build_criteria(source_commit: str, *, criteria_round: int = 1,
                   state_path: Path = STATE) -> dict:
    if criteria_round != 3:
        raise ValueError("new W3 registrations must use expanded-domain immutable round 3")
    genesis = json.loads(GENESIS.read_text())
    w1 = json.loads(W1_RESULT.read_text())
    profile = json.loads(PROFILE_MANIFEST.read_text())
    lineage = json.loads(PROFILE_LINEAGE.read_text())
    previous = json.loads(W2B_CRITERIA.read_text())
    w2_result = json.loads(W2B_RESULT.read_text())
    small_box = json.loads(STAGE_V_SMALL_BOX.read_text())
    expanded = json.loads(STAGE_V_EXPANDED.read_text())
    domain_pair = json.loads(STAGE_V_DOMAIN_PAIR.read_text())
    profile_spec = yaml.safe_load(PROFILE.read_text())

    state_path = Path(state_path)
    npz_sha = sha256(state_path)
    registered_state = genesis["state"]
    if npz_sha != registered_state["state_file_sha256"]:
        raise ValueError("canonical v16 NPZ does not match immutable genesis evidence")
    with np.load(state_path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        phi = np.asarray(archive["phi"], dtype="<f4")
    phi_c = hashlib.sha256(np.ascontiguousarray(phi).tobytes(order="C")).hexdigest()
    phi_f_bytes = np.asarray(phi, dtype="<f4", order="F").tobytes(order="F")
    phi_f = hashlib.sha256(phi_f_bytes).hexdigest()
    if metadata["state_sha256"] != registered_state["state_sha256"]:
        raise ValueError("canonical v16 SDF state metadata mismatch")
    if metadata.get("shape") != [61, 33, 25]:
        raise ValueError("canonical v16 SDF point shape mismatch")
    canonical_origin = [-1.0, -0.8, -0.6]
    flow_origin = [-2.5, -1.2, -0.9]
    flow_upper = [2.5, 1.2, 0.9]
    if metadata.get("origin_m") != canonical_origin or metadata.get("spacing_m") != 0.05:
        raise ValueError("canonical v16 SDF world-grid mapping mismatch")
    registered_w1_phi_f = w1["inputs"]["genesis_phi_fortran_raw"]["sha256"]
    if phi_c != registered_state["phi_sha256"] or phi_f != registered_w1_phi_f:
        raise ValueError("canonical v16 phi byte encodings do not match genesis/W1")
    if metadata["source_sha256"] != genesis["lineage"]["surface_stl_sha256"]:
        raise ValueError("canonical state is not bound to the registered v16 source surface")
    if sha256(STL) != profile["canonical_inputs"]["candidate"]["sha256"]:
        raise ValueError("candidate STL hash differs from v2 physical-profile manifest")
    if sha256(PROFILE) != profile["canonical_inputs"]["profile_spec"]["sha256"]:
        raise ValueError("profile YAML hash differs from v2 physical-profile manifest")
    if sha256(DOMAIN_STL) != profile["canonical_inputs"]["design_domain"]["sha256"]:
        raise ValueError("design-domain STL hash differs from v2 physical-profile manifest")
    if sha256(PROFILE_LINEAGE) != profile["candidate_lineage"]["sha256"]:
        raise ValueError("candidate-lineage evidence hash differs from v2 physical-profile manifest")
    canonical_lineage = lineage["canonical_snapshot"]
    if canonical_lineage["candidate"]["sha256"] != sha256(STL):
        raise ValueError("candidate-lineage snapshot does not bind the canonical v16 STL")
    if canonical_lineage["profile_spec"]["sha256"] != sha256(PROFILE):
        raise ValueError("candidate-lineage snapshot does not bind the registered profile YAML")
    profile_grid = profile_spec["grid"]
    profile_domain = profile_grid["domain_bounds_m"]
    profile_lower = profile_domain["lower"]
    profile_upper = profile_domain["upper"]
    profile_spacing = float(profile_grid["voxel_size_m"])
    cells_float = [(hi - lo) / profile_spacing
                   for lo, hi in zip(profile_lower, profile_upper)]
    if any(abs(value - round(value)) > 1e-12 for value in cells_float):
        raise ValueError("physical-profile bounds do not align with the registered voxel size")
    profile_cells = [int(round(value)) for value in cells_float]
    profile_shape = [count + 1 for count in profile_cells]
    flow_case = profile_spec["flow_cases"][0]
    freestream = flow_case["freestream_velocity_mps"]
    density = float(flow_case["fluid"]["density_kg_m3"])
    dynamic_viscosity = float(flow_case["fluid"]["dynamic_viscosity_pa_s"])
    reference_length = float(profile_spec["reference_values"]["length_m"])
    reference_area = float(profile_spec["reference_values"]["area_m2"])
    expected_solver_time = profile_spacing / float(freestream[0])
    expected_solver_viscosity = (dynamic_viscosity / density) * expected_solver_time / profile_spacing**2
    profile_boundaries = {
        "inlet": "far_field", "outlet": "far_field", "sideMin": "far_field",
        "sideMax": "far_field", "top": "far_field", "bottom": "moving_wall",
    }
    ground_motion = flow_case["motion_profiles"]["moving_ground"]
    if (profile_shape != list(phi.shape) or profile_lower != metadata["origin_m"]
            or profile_spacing != metadata["spacing_m"] or profile_cells != [60, 32, 24]
            or freestream != [1.0, 0.0, 0.0] or density != 1.0
            or dynamic_viscosity != 0.01 or reference_length != 0.8
            or reference_area != 0.64 or flow_case["turbulence"]["model"] != "laminar"
            or flow_case["boundary_conditions"] != profile_boundaries
            or ground_motion["kind"] != "translation"
            or ground_motion["boundary_ids"] != ["bottom"]
            or ground_motion["velocity_mps"] != freestream):
        raise ValueError("v16 adapter constants do not match the immutable physical-profile YAML")
    if (small_box.get("status") != "fail" or small_box.get("qualified") is not False
            or small_box["boundary_metrics"]["gates"]["outer_patch_backflow_and_pressure_disturbance"]["status"] != "fail"):
        raise ValueError("Stage V original small-box evidence no longer records the registered boundary failure")
    expanded_bounds = expanded["gates"]["candidate_clearance"]["preflight"]["fixed_domain_binding"]["domain_bounds_m"]
    if (expanded.get("status") != "pass" or expanded.get("qualified") is not True
            or expanded["boundary_metrics"]["gates"]["outer_patch_backflow_and_pressure_disturbance"]["status"] != "pass"
            or expanded_bounds.get("lower") != flow_origin
            or expanded_bounds.get("upper") != flow_upper):
        raise ValueError("Stage V expanded-domain physical profile does not match W3 round-3 fixture")
    pair_gate = domain_pair["gates"]["only_domain_bounds_changed"]["observed"]
    if (domain_pair.get("status") != "pass" or domain_pair.get("qualified") is not True
            or pair_gate.get("only_domain_bounds_changed") is not True
            or pair_gate.get("base_domain_bounds_m", {}).get("lower") != flow_origin
            or pair_gate.get("base_domain_bounds_m", {}).get("upper") != flow_upper
            or pair_gate.get("expanded_domain_bounds_m", {}).get("upper") != [3.5, 1.2, 0.9]
            or domain_pair["gates"]["same_candidate"]["qualified"] is not True):
        raise ValueError("Stage V same-candidate expanded-domain pair does not bind requested W3 fixture")
    if (w2_result.get("verdict") != "pass"
            or w2_result.get("gates", {}).get("T4_drag_sign") is not True
            or w2_result.get("gates", {}).get("T5_stationarity") is not True
            or previous.get("thresholds", {}).get("stationarity_relative_drift") != 0.02):
        raise ValueError("registered W2 sphere sign/stationarity precedent is unavailable")
    if metadata["source_sha256"] != sha256(STL):
        raise ValueError("SDF source lineage and canonical candidate STL disagree")
    if w1["inputs"]["genesis_state_npz"]["sha256"] != npz_sha:
        raise ValueError("W1 result does not bind this canonical v16 NPZ")
    if w1["genesis_margin_diagnosis"]["measured_zero_level_margin_m"] != 0.3499999939931499:
        raise ValueError("W1 canonical v16 margin differs from the registered W3 expectation")
    if previous["backend"]["accelerator"] != "NvidiaTeslaT4":
        raise ValueError("W2b round-5 backend is not the registered Kaggle T4 cohort")
    current_branch = subprocess.check_output(
        ["git", "-C", str(ROOT), "branch", "--show-current"], text=True,
    ).strip()
    if current_branch != "codex/kaggle-batch-migration":
        raise ValueError(f"unexpected W3 registration branch: {current_branch}")

    inputs = {name: input_entry(path) for name, path in SOURCE_INPUTS.items()}
    inputs["canonical_state_npz"] = {
        "path": "sdf_design_state.npz",
        "sha256": npz_sha,
        "location": "kaggle_dataset",
    }
    inputs["canonical_phi_fortran_raw"] = {
        "path": "canonical_v16_phi_f4_fortran.raw",
        "sha256": phi_f,
        "location": "kaggle_dataset",
        "dtype": "float32_little_endian",
        "order": "Fortran",
        "shape": list(phi.shape),
    }

    return {
        "schema_version": 1,
        "criteria_id": (
            "kaggle_w3_v16_primal_2026_09" if criteria_round == 1
            else f"kaggle_w3_v16_primal_2026_09_round{criteria_round}"
        ),
        "criteria_round": criteria_round,
        "kind": "waterlily_w3_v16_primal_criteria",
        "immutable": True,
        "status": "registered_not_run",
        "registered_before_computation": True,
        "registered_source_commit": source_commit,
        "input_dataset_id": DATASET_ID,
        "source_commit": source_commit,
        "inputs": inputs,
        "fixture_selection": {
            "purpose": "select a WaterLily finite-box fixture using independent OpenFOAM boundary evidence; no WaterLily/OpenFOAM numerical equivalence is asserted",
            "original_small_box_diagnostic": {
                "path": STAGE_V_SMALL_BOX.relative_to(ROOT).as_posix(),
                "sha256": sha256(STAGE_V_SMALL_BOX),
                "status": "fail",
                "failed_gate": "outer_patch_backflow_and_pressure_disturbance",
                "interpretation": "the original small box was boundary-contaminated under the registered OpenFOAM profile",
            },
            "expanded_domain_profile": {
                "path": STAGE_V_EXPANDED.relative_to(ROOT).as_posix(),
                "sha256": sha256(STAGE_V_EXPANDED),
                "status": "pass",
                "physical_bounds_m": [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]],
                "role": "fixture-selection precedent only",
            },
            "same_candidate_domain_pair": {
                "path": STAGE_V_DOMAIN_PAIR.relative_to(ROOT).as_posix(),
                "sha256": sha256(STAGE_V_DOMAIN_PAIR),
                "status": "pass",
                "parent_bounds_m": [[-2.5, 2.5], [-1.2, 1.2], [-0.9, 0.9]],
                "child_bounds_m": [[-2.5, 3.5], [-1.2, 1.2], [-0.9, 0.9]],
                "same_candidate": True,
                "openfoam_cd_parent_child": [1.1693991415068494, 1.17036295130137],
                "openfoam_downforce_parent_child": [0.7565514657808219, 0.7573548684589041],
                "role": "fixture-selection precedent only; these values are not WaterLily targets",
            },
            "force_sign_precedent": {
                "path": W2B_RESULT.relative_to(ROOT).as_posix(),
                "sha256": sha256(W2B_RESULT),
                "w2_round5_criteria_path": W2B_CRITERIA.relative_to(ROOT).as_posix(),
                "w2_round5_criteria_sha256": sha256(W2B_CRITERIA),
                "positive_drag_gate_passed": True,
                "force_convention": "drag=+Fx; downforce=-Fz",
            },
        },
        "geometry": {
            "state_npz_path": "sdf_design_state.npz",
            "state_sha256": registered_state["state_sha256"],
            "state_npz_sha256": npz_sha,
            "source_surface_path": STL.relative_to(ROOT).as_posix(),
            "source_surface_sha256": sha256(STL),
            "design_domain_sha256": sha256(DOMAIN_STL),
            "phi_c_order_sha256": phi_c,
            "phi_fortran_sha256": phi_f,
            "point_shape": [61, 33, 25],
            "cell_shape": [60, 32, 24],
            "canonical_sdf_origin_m": canonical_origin,
            "spacing_m": profile_spacing,
            "margin_gate_m": 0.15,
            "expected_margin_m": 0.3499999939931499,
            "margin_tolerance_m": 1e-6,
            "sign_convention": "phi < 0 solid / phi > 0 fluid",
        },
        "profile_adapter": {
            "source_profile_id": profile["physical_profile"]["profile_id"]
                if "profile_id" in profile["physical_profile"]
                else "stage_v_v16_project_matched_re_laminar_moving_ground_far_field_v2",
            "source_profile_sha256": profile["physical_profile_sha256"],
            "profile_spec_sha256": sha256(PROFILE),
            "cell_dims": [100, 48, 36],
            "point_shape": profile_shape,
            "flow_origin_m": flow_origin,
            "physical_box_m": [[flow_origin[0], flow_upper[0]],
                               [flow_origin[1], flow_upper[1]],
                               [flow_origin[2], flow_upper[2]]],
            "world_per_solver_m": profile_spacing,
            "solver_time_unit_s": expected_solver_time,
            "solver_length": reference_length / profile_spacing,
            "solver_velocity": 1.0,
            "reynolds_length_m": reference_length,
            "reynolds": density * float(freestream[0]) * reference_length / dynamic_viscosity,
            "solver_viscosity": expected_solver_viscosity,
            "ground_velocity_mps": freestream,
            "ground_model": "embedded planar half-space at the lower-z domain plane; +x wall velocity from the registered translation profile",
            "x_max_boundary": "WaterLily convective exit",
            "side_top_normal_velocity": "zero",
            "side_top_tangential_condition": "zero-Neumann",
            "pressure_boundary": "WaterLily projection pressure; no per-patch freestreamPressure input",
            "source_profile_equivalent": False,
            "physical_profile_qualified": False,
            "limitation": "WaterLily 1.8.0 native outer BCs do not reproduce the source profile's per-patch OpenFOAM freestreamVelocity/freestreamPressure semantics.",
        },
        "backend": {
            "backend": "kaggle_background",
            "machine_shape": previous["backend"]["accelerator"],
            "accelerator": previous["backend"]["accelerator"],
            "gpu_name": "Tesla T4",
            "gpu_count": previous["backend"]["gpu_count"],
            "selected_gpu_policy": "visible GPU index 0; record the selected UUID for this run",
            "driver_version": previous["backend"]["driver_version"],
            "cuda_driver_api_version": previous["backend"]["cuda_driver_api_version"],
            "cuda_runtime_version": previous["backend"]["cuda_runtime_version"],
            "cuda_jl_version": previous["backend"]["cuda_jl_version"],
            "compute_capability": previous["backend"]["compute_capability"],
            "julia_version": previous["backend"]["julia_version"],
            "julia_threads": 1,
            "waterlily_version": previous["backend"]["waterlily_version"],
            "cuda_visible_devices": "0",
            "julia_archive_sha256": "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a",
        },
        "measurement": {
            "t_end_t_u_l": 120.0,
            "burn_in_t_u_l": 80.0,
            "force_sampling": "every 8 solver steps",
            "sample_every_solver_steps": 8,
            "primary_force_metric": "trapezoidal physical-time-weighted mean over samples in [80,120] tU/L",
            "minimum_window_samples": 4,
            "force_window_t_u_l": [80.0, 120.0],
            "endpoint_policy": "if exact 80 or 120 samples are absent, linearly interpolate from bracketing raw force samples",
            "integration": "trapezoidal time-weighted means on exact [80,120], [80,100], and [100,120] intervals",
            "stationarity": {
                "relative_half_window_drift_max": 0.02,
                "formula": "abs(mean_first - mean_second) / max(abs(mean_whole), eps(Float64))",
                "mean_definition": "independent trapezoidal physical-time-weighted means on exact endpoint-clipped [80,100], [100,120], and [80,120] windows",
                "quantities": ["drag", "downforce"],
                "precedent": "inherited before measurement from registered W2 sphere capability criterion; not selected from W3 v3 values",
                "precedent_criteria_path": W2B_CRITERIA.relative_to(ROOT).as_posix(),
                "precedent_criteria_sha256": sha256(W2B_CRITERIA),
            },
            "reference_area_m2": reference_area,
            "spacing_m": profile_spacing,
            "density_kg_m3": density,
            "freestream_mps": freestream,
            "drag_direction": [1.0, 0.0, 0.0],
            "downforce_direction": [0.0, 0.0, -1.0],
            "force_integration_body": "canonical v16 candidate GridSDF only; do not integrate the auxiliary moving-ground half-space",
            "solver_precision": "Float32",
            "memory": "CuArray",
            "runtime_limit_s": 1800.0,
            "host_recompute_relative_tolerance": 1e-9,
            "force_component_relative_tolerance": 1e-6,
            "force_component_absolute_tolerance": 1e-8,
        },
        "acceptance": {
            "gates": [
                "T0 all registered source and dataset inputs match their SHA-256 values",
                "T1 canonical state, source surface, C/Fortran phi hashes, GPU round-trip and solver grid identity match",
                "T2 CPU-side W1 margin gate is 0.15 m and measured margin matches the registered v16 value within 1e-6 m",
                "T3 mapped adapter semantics are present and remain explicitly non-equivalent/unqualified",
                "T4 registered single-T4 visible-device, GPU inventory, driver/runtime and Julia/WaterLily identity match",
                "T5 simulation reaches tU/L=120",
                "T6 velocity, pressure and candidate-force samples are finite, with at least four registered window samples",
                "T7 drag is along +x, downforce is the -z projection without a sign/magnitude threshold, all total force components close pressure plus viscous, and host exact-window recomputation matches",
                "T8 run is within the per-run wall-time and VRAM bounds",
                "T9 exact source commit and kernel runner identity match preregistration",
                "T10 exact-window relative half-window drift for drag and downforce is at most 0.02",
            ],
            "stationarity_gate": True,
            "stationarity_threshold_precedent": "registered W2 sphere capability convention",
            "downforce_sign_or_magnitude_gate": False,
            "physical_profile_equivalence_gate": False,
            "claim_scope": "canonical v16 SDF met the registered integrity, force, and stationarity contract on the registered WaterLily finite-box approximation",
        },
        "claims_not_supported": [
            "equivalence to the registered OpenFOAM freestreamPressure/freestreamVelocity outer patches",
            "Stage V physical-profile qualification",
            "grid/domain convergence, absolute downforce or target-vehicle qualification",
            "gradient, reverse-mode, topology, optimization or shape-update qualification",
            "high-Reynolds-number or full-vehicle FSAE qualification",
        ],
        "flags": {
            "waterlily_v16_primal_qualified": False,
            "physical_profile_qualified": False,
            "grid_response_qualified": False,
            "shape_update_allowed": False,
            "sdf_gradient_qualified": False,
            "waterlily_reverse_cpu_qualified": False,
            "waterlily_reverse_cuda_qualified": False,
            "topology_birth_qualified": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify an existing immutable registration")
    parser.add_argument("--round", type=int, default=1,
                        help="immutable W3 criteria round number (default: 1)")
    parser.add_argument("--state", type=Path, default=STATE,
                        help="canonical v16 state NPZ used to bind the dataset inputs")
    args = parser.parse_args()
    output = criteria_output_path(args.round)
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if args.check:
        if not output.is_file() or not sidecar.is_file():
            raise SystemExit("W3 criteria or its SHA sidecar is missing")
        actual = sha256(output)
        expected = sidecar.read_text().strip()
        if actual != expected:
            raise SystemExit("W3 criteria SHA sidecar mismatch")
        print(actual)
        return 0
    if output.exists() or sidecar.exists():
        raise SystemExit("W3 criteria already exists; immutable registration will not be overwritten")
    source_commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(ROOT), "status", "--porcelain"], text=True,
    ).strip()
    if status:
        raise SystemExit("commit and push the W3 source before registering immutable criteria")
    if sha256(T4_PROJECT) != "e4b56407b8df30b5abe0e26fede29520dbbf69c0580be39bb7d5e657bb984194":
        raise SystemExit("pinned T4 project changed")
    if sha256(T4_MANIFEST) != "c537ae8ef4eaacf7a6e8e906fce8f524a20b9f2ce7e571db9de2a50ec9ed4707":
        raise SystemExit("pinned T4 manifest changed")
    criteria = build_criteria(source_commit, criteria_round=args.round,
                              state_path=args.state)
    output.write_text(json.dumps(criteria, indent=2, sort_keys=True, allow_nan=False) + "\n")
    digest = sha256(output)
    sidecar.write_text(digest + "\n")
    print(json.dumps({"criteria_path": output.relative_to(ROOT).as_posix(),
                      "criteria_sha256": digest,
                      "source_commit": source_commit}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
