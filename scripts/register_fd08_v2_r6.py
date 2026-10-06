#!/usr/bin/env python3
"""Build the frozen R6 input inventory and, after source integration, criteria.

This tool only constructs/validates geometry and immutable input metadata. It
never reads force data or starts a solver. The `--register` operation refuses
to overwrite an existing criteria file.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.candidate_c_identity import load_candidate_c_identity
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.fd08_v2_campaign import (
    DIRECTION_IDS,
    FORMAL_EPSILON_MM,
    FORMAL_INTERVAL_INDICES,
    FLOAT32_DIRECTION_RELATIVE_L2_LIMIT,
    MARGIN_GATE_M,
    MARGIN_TOLERANCE_M,
    R6_EPSILON_MM,
    build_state_inventory,
    direction_diagnostics,
    false_flags,
    generate_p1,
    sha256_bytes,
    sha256_json,
)
from cfd_sdf.gradients.directional_fd import direction_sha256, generate_directions, phi_sha256


CANONICAL_NPZ_SHA256 = "7a972b330c11d6580c49de4cba9b5f4a0b2cb664dda67e4f7053c280655feb31"
CANONICAL_PHI_FORTRAN_SHA256 = "e3966d87c0ddb0d3ff9a6ee096c94221d0d4cccff77221ba84987ef5faa04431"
CANONICAL_STATE_SHA256 = "02f48f6488be4f5d772c3ec515d4860b00e0e4a84d38aa56b187c82c1a615dcb"
CANONICAL_SOURCE_SURFACE_SHA256 = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
EXPECTED_PROTECTED_DIRECTIONS = {
    "D0_interface_offset": "8b5773b7d404cc21819078085eddeae437cad619472910fcac17430b2b6be3b5",
    "D1_filtered_seed11": "4da3513780c3ba9b2ab91837911d46a2cab362e9a561eedb18468b424f81d4f5",
    "D2_filtered_seed2026": "bb1eeaf0cdd43bc71085499c853f24eae6335e030851dfc0f9b581f4f5aa8fe8",
}
DEFAULT_STATE = Path(
    "/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v17/sdf_design_state.npz"
)
DEFAULT_DATASET = ROOT / "work/kaggle_fd08_v2_r6_dataset"
DEFAULT_PREFLIGHT = ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/preflight.json"
DEFAULT_CRITERIA = ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_criteria.json"

RUNTIME = {
    "accelerator": "NvidiaTeslaT4",
    "machine_shape": "NvidiaTeslaT4",
    "gpu_name": "Tesla T4",
    "gpu_count": 2,
    "cuda_visible_devices": "0",
    "compute_capability": "7.5.0",
    "cuda_driver_api_version": "13.3.0",
    "cuda_runtime_version": "12.8.0",
    "driver_minor_version_policy": "recorded_not_gated",
    "julia_version": "1.12.6",
    "julia_threads": 1,
    "julia_archive_sha256": "bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a",
    "cuda_jl_version": "6.3.1",
    "waterlily_version": "1.8.0",
    "waterlily_backend": "KernelAbstractions",
    "precision": "Float32",
    "memory": "CuArray",
}
KERNEL_ID = "ramhachi888/cfd-opt-sdf-fd08-v2-r6-and-formal"
SOURCE_FILES = {
    "kaggle_budget_preflight": "scripts/check_fd08_v2_kaggle_budget.py",
    "campaign": "src/cfd_sdf/fd08_v2_campaign.py",
    "gate": "src/cfd_sdf/fd08_v2_gate.py",
    "params": "src/cfd_sdf/fd08_v2_gate_params.json",
    "direction_generator": "src/cfd_sdf/gradients/directional_fd.py",
    "state_identity": "src/cfd_sdf/design/sdf_state.py",
    "candidate_c_identity_loader": "src/cfd_sdf/candidate_c_identity.py",
    "candidate_c_job": "scripts/waterlily_xfid_candidate_c_job.jl",
    "setup_rehearsal_job": "scripts/waterlily_fd08_v2_setup_rehearsal.jl",
    "setup_rehearsal_verifier": "scripts/verify_fd08_v2_setup_rehearsal.py",
    "t4_smoke": "scripts/w0b_t4_smoke.jl",
    "julia_project": "julia/CFDSDFWaterLilyT4/Project.toml",
    "julia_manifest": "julia/CFDSDFWaterLilyT4/Manifest.toml",
    "candidate_c_contract": "docs/evidence/candidate_c_composite_operator_identity_v1_2026_10.json",
    "candidate_c_contract_sha": "docs/evidence/candidate_c_composite_operator_identity_v1_2026_10.json.sha256",
    "flow24_precedent": "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10_round2.json",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "w4_sensitivity_module": "julia/CFDSDFWaterLily/src/V16W4Sensitivity.jl",
    "numeric_c4_reference": "scripts/analyze_fd08_v2_numeric_contract.py",
    "numeric_c5_envelope": "scripts/fd08_v2_forward_error.py",
    "r6_registrar": "scripts/register_fd08_v2_r6.py",
    "setup_preparer": "scripts/prepare_fd08_v2_setup_rehearsal.py",
    "r6_verifier": "scripts/verify_fd08_v2_r6.py",
    "r6_analyzer": "scripts/analyze_fd08_v2_r6.py",
    "formal_prediction_source": "src/cfd_sdf/fd08_v2_campaign.py",
    "formal_registrar": "scripts/register_fd08_v2_formal.py",
    "formal_verifier": "scripts/verify_fd08_v2_formal.py",
    "formal_analyzer": "scripts/analyze_fd08_v2_formal.py",
    "kernel_runner": "infra/kaggle/kernel_fd08_v2_r6/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_fd08_v2_r6/kernel-metadata.json",
    "campaign_tests": "tests/test_fd08_v2_campaign.py",
    "gate_tests": "tests/test_fd08_v2_gate.py",
    "campaign_artifacts": "scripts/fd08_v2_campaign_io.py",
    "preflight_evidence": "docs/evidence/fd08_v2_r6_2026_10_06/preflight.json",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_budget_evidence(path: Path, phase: str, solver_cap_s: int,
                         kernel_allowance_s: int) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise ValueError(f"{phase} registration requires a CLI-backed Kaggle budget preflight")
    evidence_sha = digest(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != evidence_sha:
        raise ValueError(f"{phase} budget preflight SHA sidecar mismatch")
    budget = json.loads(path.read_text())
    expected_checks = {
        "cli_timeout_option_available",
        "kernel_allowance_within_platform_session_limit",
        "kernel_allowance_within_current_gpu_quota",
    }
    checks = budget.get("checks")
    requested = budget.get("requested", {})
    captured = datetime.fromisoformat(budget.get("captured_utc", "").replace("Z", "+00:00"))
    age_s = (datetime.now(timezone.utc) - captured).total_seconds()
    if (budget.get("kind") != "fd08_v2_kaggle_budget_preflight"
            or budget.get("phase") != phase
            or budget.get("status") != "PASS_CAPABILITY_PREFLIGHT"
            or budget.get("cli_version") != "Kaggle CLI 2.2.4"
            or not any("--timeout" in line for line in budget.get("timeout_option_help_lines", []))
            or requested.get("solver_wall_time_cap_s") != solver_cap_s
            or requested.get("kernel_execution_allowance_s") != kernel_allowance_s
            or budget.get("platform_max_cpu_gpu_session_seconds") != 43200
            or budget.get("platform_max_cpu_gpu_session_seconds", 0) < kernel_allowance_s
            or budget.get("gpu_quota_remaining_seconds_floor", 0) < kernel_allowance_s
            or not isinstance(checks, dict) or set(checks) != expected_checks
            or not all(value is True for value in checks.values())
            or budget.get("runtime_guarantee") is not False
            or age_s < 0 or age_s > 24 * 60 * 60):
        raise ValueError(f"{phase} Kaggle platform/quota caps are not currently available as registered")
    return budget, evidence_sha


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def load_state(path: Path) -> tuple[SDFDesignState, bytes]:
    raw_npz = path.read_bytes()
    if hashlib.sha256(raw_npz).hexdigest() != CANONICAL_NPZ_SHA256:
        raise ValueError("canonical v17 NPZ SHA-256 mismatch")
    state = SDFDesignState.load(path)
    if state.state_sha256 != CANONICAL_STATE_SHA256:
        raise ValueError("canonical v17 state identity mismatch")
    if phi_sha256(state.phi, order="F") != CANONICAL_PHI_FORTRAN_SHA256:
        raise ValueError("canonical v17 raw Float32 phi hash mismatch")
    if state.source_sha256 != CANONICAL_SOURCE_SURFACE_SHA256:
        raise ValueError("canonical v17 source-surface identity mismatch")
    if state.shape != (121, 65, 49) or state.origin_m != (-1.0, -0.8, -0.6) or state.spacing_m != 0.025:
        raise ValueError("canonical v17 grid geometry mismatch")
    return state, raw_npz


def source_inventory() -> dict[str, dict[str, str]]:
    return {name: {"path": relative, "sha256": digest(ROOT / relative)}
            for name, relative in SOURCE_FILES.items()}


def make_contract(state: SDFDesignState, state_path: Path, dataset_dir: Path,
                  preflight_path: Path, source_commit: str | None) -> tuple[dict[str, Any], dict[str, bytes]]:
    parent, canonical_npz = load_state(state_path)
    if state.state_sha256 != parent.state_sha256:
        raise ValueError("internal canonical-state identity changed")
    protected = generate_directions(parent)
    for name, expected in EXPECTED_PROTECTED_DIRECTIONS.items():
        actual = direction_sha256(protected[name])
        if actual != expected:
            raise ValueError(f"protected direction hash changed: {name}={actual}")
    p1, p1_definition = generate_p1(parent)
    directions = {**protected, "P1_upstream_lobe": p1}
    diagnostics = direction_diagnostics(parent, directions)
    inventory, blobs, float32_audits = build_state_inventory(parent, directions)

    files: dict[str, bytes] = {"baseline_v17.sdf_design_state.npz": canonical_npz}
    for row in inventory:
        raw_name = row["phi_raw_file"]
        files[raw_name] = blobs[raw_name]
        if row["kind"] == "baseline":
            row["npz_file"] = "baseline_v17.sdf_design_state.npz"
            row["npz_sha256"] = hashlib.sha256(canonical_npz).hexdigest()
        else:
            target = dataset_dir / f"{row['name']}.sdf_design_state.npz"
            matching = next((state for state in _all_children(parent, directions)
                             if state[1] == row["name"]), None)
            if matching is None:
                raise AssertionError(f"could not reconstruct state {row['name']}")
            child = matching[0]
            with tempfile.TemporaryDirectory(prefix="fd08-v2-state-") as temp:
                temporary_npz = Path(temp) / target.name
                child.save(temporary_npz)
                npz_bytes = temporary_npz.read_bytes()
            row["npz_file"] = target.name
            row["npz_sha256"] = hashlib.sha256(npz_bytes).hexdigest()
            files[target.name] = npz_bytes

    preflight = {
        "schema_version": 1,
        "kind": "fd08_v2_r6_solver_free_preflight",
        "status": "PASS_PRE_REGISTRATION_GATES",
        "evidence_scope": "geometry_direction_float32_and_inventory_only_no_solver_response",
        "T2_parameter_sha256": digest(ROOT / "src/cfd_sdf/fd08_v2_gate_params.json"),
        "T2_parameter_classification": "arbitrary-provisional diagnostic operating contract only",
        "canonical": {
            "npz_sha256": CANONICAL_NPZ_SHA256,
            "state_sha256": parent.state_sha256,
            "phi_fortran_sha256": CANONICAL_PHI_FORTRAN_SHA256,
            "shape": list(parent.shape),
            "origin_m": list(parent.origin_m),
            "spacing_m": parent.spacing_m,
            "narrow_band_width_m": parent.narrow_band_width_m,
            "source_surface_sha256": parent.source_sha256,
            "active_node_count": int(np.count_nonzero(parent.design_mask & ~parent.fixed_solid_mask & ~parent.forbidden_mask & ~parent.root_mask)),
        },
        "protected_direction_expected_hashes": EXPECTED_PROTECTED_DIRECTIONS,
        "directions": diagnostics,
        "P1_generation": p1_definition,
        "epsilon_ladder_mm": list(R6_EPSILON_MM),
        "epsilon_ladder_m": [value / 1000.0 for value in R6_EPSILON_MM],
        "formal_epsilon_mm_fixed_formula": {
            "interval_indices": list(FORMAL_INTERVAL_INDICES),
            "formula": "sqrt(e_i*e_(i+1))",
            "values": list(FORMAL_EPSILON_MM),
        },
        "float32_centered_audits": float32_audits,
        "state_count": len(inventory),
        "state_order": inventory,
        "phi_state_bytes_pairwise_unique_including_baseline": len({
            blobs[row["phi_raw_file"]] for row in inventory
        }) == 49,
        "candidate_numerical_comparison": {
            "C4": "semantic comparison against high-precision Decimal reference",
            "C5": "conditional fit/operand backward-error engineering envelope; not an LAPACK/SVD guarantee",
            "C1_C2_C3": "diagnostic only",
        },
    }
    if not preflight["phi_state_bytes_pairwise_unique_including_baseline"]:
        raise ValueError("R6 phi bytes are not unique")
    preflight_blob = json.dumps(preflight, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    if preflight_path.exists() and preflight_path.read_bytes() != preflight_blob:
        raise FileExistsError(f"refusing to replace different preflight evidence: {preflight_path}")
    if not preflight_path.exists():
        preflight_path.parent.mkdir(parents=True, exist_ok=True)
        preflight_path.write_bytes(preflight_blob)

    dataset_files = {
        filename: hashlib.sha256(content).hexdigest()
        for filename, content in files.items()
    }
    contract = {
        "schema_version": 1,
        "kind": "fd08_v2_r6_calibration",
        "evidence_class": "immutable_candidate_c_local_directional_response_calibration",
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "criteria_id": "FD08-V2-R6-2026-10-06",
        "kernel_id": KERNEL_ID,
        "input_dataset_id": "ramhachi888/cfd-opt-sdf-fd08-v2-r6",
        "source_commit": source_commit,
        "canonical_state": preflight["canonical"],
        "operator_identity": load_candidate_c_identity(ROOT),
        "numeric_contract": {
            "version": "FD08-v2-N1-C4-C5-T2",
            "fit_epsilon_unit": "mm",
            "response_unit": "N",
            "slope_display_unit": "N/m",
            "arithmetic": "N1",
            "models": {
                "A": "S(epsilon)=g*epsilon+c*epsilon^3",
                "B": "S(epsilon)=g*epsilon+k*epsilon*abs(epsilon)",
            },
            "estimator": "OLS pilot on exactly each selected point set; construct pilot variance; one WLS pass",
            "objective_weight": "w_i=1/(sigma0_n^2+(rho*S_pilot_i)^2)",
            "row_multiplier": "sqrt(w_i)=1/sqrt(sigma0_n^2+(rho*S_pilot_i)^2)",
            "covariance": "inverse(X.T @ W @ X), nominal conditional plug-in; no chi-square/dof rescale; no sandwich",
            "dimensionless_diagnostics": "relative SE, nested shift, and model difference formed from internal N/mm values",
            "C4": "semantic comparison against exact binary64 inputs evaluated by the high-precision Decimal reference",
            "C5": "conditional fit/operand backward-error engineering envelope, not a universal LAPACK/SVD theorem",
            "C1_C2_C3": "diagnostics only; never reclassify historical Stage 1 results",
            "T2_parameter_sha256": digest(ROOT / "src/cfd_sdf/fd08_v2_gate_params.json"),
            "T2_parameter_classification": "arbitrary-provisional diagnostic operating contract only",
            "parameters": json.loads((ROOT / "src/cfd_sdf/fd08_v2_gate_params.json").read_text()),
        },
        "direction_inventory": {
            "coverage": "COV-A: all four directions and both responses must pass; 8/8 required",
            "directions": DIRECTION_IDS,
            "hashes": {key: value["sha256"] for key, value in diagnostics["directions"].items()},
            "P1_generation": p1_definition,
            "duplicate_gate": f"absolute cosine < {DUPLICATE_LIMIT_TEXT}",
        },
        "ladder": {
            "rule": "numpy.geomspace(0.5,5,6), float64 values serialized with 17 significant digits",
            "epsilon_mm": list(R6_EPSILON_MM),
            "epsilon_m": [value / 1000.0 for value in R6_EPSILON_MM],
            "nominal_coefficient_semantics": "epsilon_m multiplies the max=1 phi direction; do not replace with effective physical displacement",
            "jitter": "J1; none; exact repeats are not a noise estimate",
        },
        "measurement": {
            "case_id": "flow_24",
            "case": {
                "case_id": "flow_24",
                "flow_dims": [150, 72, 54],
                "flow_spacing_m": 0.03333333333333333,
                "density_kg_m3": 1.0,
                "freestream_mps": [1.0, 0.0, 0.0],
                "reference_length_m": 0.8,
                "reference_area_m2": 0.64,
                "solver_length": 24.0,
                "solver_time_unit_s": 0.03333333333333333,
                "solver_viscosity": 0.3,
                "reynolds": 80.0,
                "dynamic_viscosity_pa_s": 0.01,
                "precedent_criteria_path": "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10_round2.json",
                "precedent_criteria_sha256": digest(ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10_round2.json"),
            },
            "time_window_t_u_l": [80.0, 120.0],
            "force_unit": "N",
            "solver_wall_time_cap_s": 6600,
            "kernel_execution_allowance_s": 11200,
            "per_state_timeout_s": 1500,
            "aggregate_solver_time_definition": "sum of registered per-state Julia wall_seconds excluding each state's first compile/warmup step, consistent with the bound W4 job",
            "candidate_operator": "CandidateCWaterLilyBody(NormalFloorWaterLilyBody(candidate_grid))",
            "qualification_claim": "frozen Candidate C/v17/flow_24 local diagnostic only",
        },
        "runtime": RUNTIME,
        "state_inventory": inventory,
        "expected_state_count": 49,
        "direction_pair_float32_audits": float32_audits,
        "geometry_reject_gates": {
            "finite": True,
            "canonical_shape_dtype_order": "point_shape, little-endian float32; raw file serialized Fortran order",
            "support_outside_active_exactly_zero": True,
            "protected_fixed_forbidden_root_constraints_preserved": True,
            "no_geometry_repair": True,
            "max_abs_normalization_tolerance": 2e-7,
            "minimum_zero_level_margin_m": MARGIN_GATE_M,
            "margin_tolerance_m": MARGIN_TOLERANCE_M,
            "relative_l2_error_limit": FLOAT32_DIRECTION_RELATIVE_L2_LIMIT,
            "phi_bytes_pairwise_unique_including_baseline": True,
        },
        "dataset_files": dataset_files,
        "dataset_manifest_file": "fd08_v2_dataset_manifest.json",
        "artifact_paths": {
            "criteria": "criteria.json",
            "output_root": "fd08_v2_r6",
            "result": "fd08_v2_r6/result.json",
            "sha_manifest": "fd08_v2_r6/sha256.json",
            "terminal_marker": "fd08_v2_r6/DONE",
        },
        "source_inputs": source_inventory(),
        "preflight": {
            "path": preflight_path.relative_to(ROOT).as_posix(),
            "sha256": digest(preflight_path),
        },
        "decision_tree": {
            "per_series": "PASS/FAIL/UNRESOLVED per direction and response using the six registered gate items",
            "aggregate": "8/8 PASS => R6 PASS; any FAIL => R6 FAIL; otherwise any UNRESOLVED => R6 UNRESOLVED",
            "coverage": "COV-A; do not drop D1 or alter 4/4 direction coverage",
        },
        "formal_preregistration_template": {
            "pre_result_code_fixed": True,
            "state_count": 25,
            "state_order_rule": "baseline plus 4 directions x 3 formal epsilon x plus/minus",
            "epsilon_rule": "For calibration e[0..5], indices {0,2,4}; formal=sqrt(e[i]*e[i+1])",
            "epsilon_mm": list(FORMAL_EPSILON_MM),
            "prediction_model": "calibration full six-point Model A only; no formal refit",
            "prediction": "S_pred=x.T beta; sigma_pred^2=sigma0^2+(rho*S_pred)^2+x.T C x",
            "pass": "finite/integrity; nonzero same sign; both magnitudes >= k_mag*sigma0; abs error <= max(3*sigma_pred,tol_hold*abs(S_pred))",
            "semantic_scope": "deterministic-solver interior interpolation validation only",
            "prediction_source_sha256": digest(ROOT / "src/cfd_sdf/fd08_v2_campaign.py"),
            "formal_registrar_sha256": digest(ROOT / "scripts/register_fd08_v2_formal.py"),
            "formal_verifier_sha256": digest(ROOT / "scripts/verify_fd08_v2_formal.py"),
            "formal_analyzer_sha256": digest(ROOT / "scripts/analyze_fd08_v2_formal.py"),
        },
        "retry_policy": {
            "pre_registration_source_harness_input_error": "repair, rerun applicable checks, integrate clean source, then create new criteria",
            "post_registration_transient_external_infrastructure_only": "retry same immutable criteria and source, save every attempt",
            "post_registration_source_fix_required": "do not amend old criteria; preserve attempt and create a new preregistration from a new source identity",
            "scientific_fail_or_unresolved": "no retry or threshold/source/direction/ladder/model changes",
        },
        "qualification_flags": false_flags(),
        "not_claimed": [
            "#23 numerical precision delta", "gradient accuracy", "physical correctness", "grid independence",
            "epsilon-to-zero true derivative", "noise validation", "direction generalization",
            "OpenFOAM absolute agreement", "field gradient, reverse, optimizer, topology, or shape-update qualification",
        ],
    }
    return preflight, files, contract


def _all_children(parent: SDFDesignState, directions: dict[str, np.ndarray]):
    from cfd_sdf.fd08_v2_campaign import construct_state

    for direction_id in DIRECTION_IDS:
        for epsilon in R6_EPSILON_MM:
            for sign, sign_name in ((1, "plus"), (-1, "minus")):
                child, _ = construct_state(parent, directions[direction_id], epsilon, sign)
                name = f"{direction_id}__e{epsilon:.17g}mm__{sign_name}"
                yield child, name


DUPLICATE_LIMIT_TEXT = "0.95"


def prepare(args: argparse.Namespace) -> int:
    state, _ = load_state(args.state)
    args.dataset_dir.mkdir(parents=True, exist_ok=True)
    if not args.register and any(args.dataset_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty dataset: {args.dataset_dir}")
    preflight, files, contract = make_contract(state, args.state, args.dataset_dir, args.preflight, None)
    if args.register:
        if not args.source_commit or len(args.source_commit) != 40:
            raise ValueError("--register requires the exact 40-character integration source commit")
        if args.criteria.exists() or args.criteria.with_suffix(args.criteria.suffix + ".sha256").exists():
            raise FileExistsError(f"refusing to overwrite immutable criteria: {args.criteria}")
        contract["source_commit"] = args.source_commit
        measurement = contract["measurement"]
        budget, budget_sha = load_budget_evidence(
            args.budget_evidence, "r6", measurement["solver_wall_time_cap_s"],
            measurement["kernel_execution_allowance_s"],
        )
        contract["budget_feasibility"] = {
            "evidence_path": args.budget_evidence.relative_to(ROOT).as_posix(),
            "evidence_sha256": budget_sha,
            "captured_utc": budget["captured_utc"],
            "cli_version": budget["cli_version"],
            "gpu_quota_remaining_hours": budget["gpu_quota_remaining_hours"],
            "platform_max_cpu_gpu_session_seconds": budget["platform_max_cpu_gpu_session_seconds"],
            "requested_kernel_execution_allowance_s": measurement["kernel_execution_allowance_s"],
            "status": budget["status"],
        }
        if not args.setup_evidence or not args.setup_evidence.is_file():
            raise ValueError("R6 registration requires the completed setup-only T4 rehearsal evidence")
        setup_sha = digest(args.setup_evidence)
        setup_sidecar = args.setup_evidence.with_suffix(args.setup_evidence.suffix + ".sha256")
        if not setup_sidecar.is_file() or setup_sidecar.read_text().strip() != setup_sha:
            raise ValueError("setup rehearsal evidence SHA sidecar mismatch")
        setup_record = json.loads(args.setup_evidence.read_text())
        if (setup_record.get("kind") != "fd08_v2_setup_rehearsal_verified"
                or setup_record.get("status") != "PASS_SETUP_ONLY"
                or setup_record.get("source_commit") != args.source_commit
                or setup_record.get("force_history_present") is not False):
            raise ValueError("setup rehearsal is not a valid non-scientific pass on this source commit")
        contract["setup_rehearsal"] = {
            "evidence_path": args.setup_evidence.relative_to(ROOT).as_posix(),
            "evidence_sha256": setup_sha,
            "criteria_sha256": setup_record["criteria_sha256"],
            "kernel_version": setup_record["kernel_version"],
            "output_manifest_sha256": setup_record["output_manifest_sha256"],
            "evidence_class": "setup_only_not_calibration_or_formal_science",
        }
        files["setup_rehearsal_evidence.json"] = args.setup_evidence.read_bytes()
        files["kaggle_budget_preflight.json"] = args.budget_evidence.read_bytes()
        criteria_blob = json.dumps(contract, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        contract_sha = hashlib.sha256(criteria_blob).hexdigest()
        files["criteria.json"] = criteria_blob
        files["criteria.json.sha256"] = (contract_sha + "\n").encode()
        manifest = {
            "kind": "fd08_v2_r6_private_dataset_manifest",
            "criteria_sha256": contract_sha,
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()
            if name not in {"fd08_v2_dataset_manifest.json"}},
        }
        files["fd08_v2_dataset_manifest.json"] = json.dumps(
            manifest, sort_keys=True, indent=2, allow_nan=False
        ).encode() + b"\n"
        dataset_file_map = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()
                            if name not in {"criteria.json", "criteria.json.sha256",
                                            "fd08_v2_dataset_manifest.json"}}
        contract["dataset_files"] = dataset_file_map
        # The registered dataset hash map is not self-referential: state-file bytes are
        # already present and immutable; write the final criteria with exact hashes.
        criteria_blob = json.dumps(contract, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        contract_sha = hashlib.sha256(criteria_blob).hexdigest()
        files["criteria.json"] = criteria_blob
        files["criteria.json.sha256"] = (contract_sha + "\n").encode()
        manifest = {
            "kind": "fd08_v2_r6_private_dataset_manifest",
            "criteria_sha256": contract_sha,
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()
                      if name != "fd08_v2_dataset_manifest.json"},
        }
        files["fd08_v2_dataset_manifest.json"] = json.dumps(
            manifest, sort_keys=True, indent=2, allow_nan=False
        ).encode() + b"\n"
        args.criteria.parent.mkdir(parents=True, exist_ok=True)
        args.criteria.write_bytes(criteria_blob)
        args.criteria.with_suffix(args.criteria.suffix + ".sha256").write_text(contract_sha + "\n")
    metadata = {
        "title": "CFD Opt SDF FD08 V2 Private Inputs",
        "id": "ramhachi888/cfd-opt-sdf-fd08-v2-r6",
        "licenses": [{"name": "other"}],
    }
    metadata_path = args.dataset_dir / "dataset-metadata.json"
    if metadata_path.exists():
        if json.loads(metadata_path.read_text()) != metadata:
            raise FileExistsError("refusing to replace different Kaggle dataset metadata")
    else:
        write_json(metadata_path, metadata)
    for name, data in files.items():
        path = args.dataset_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != data:
                raise FileExistsError(f"refusing to replace different dataset file: {path}")
        else:
            path.write_bytes(data)
    print(json.dumps({
        "preflight": str(args.preflight),
        "preflight_sha256": digest(args.preflight),
        "state_count": len(contract.get("state_inventory", [])),
        "status": preflight["status"],
        "dataset_file_count": len(files),
        "criteria_path": str(args.criteria) if args.register else None,
        "criteria_sha256": hashlib.sha256(args.criteria.read_bytes()).hexdigest() if args.register else None,
    }, sort_keys=True, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--source-commit")
    parser.add_argument("--setup-evidence", type=Path)
    parser.add_argument("--budget-evidence", type=Path)
    return prepare(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
