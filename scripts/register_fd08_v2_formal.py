#!/usr/bin/env python3
"""Register the pre-frozen formal predict-then-run round after R6 PASS only."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.candidate_c_identity import load_candidate_c_identity
from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.fd08_v2_campaign import (
    DIRECTION_IDS,
    FORMAL_EPSILON_MM,
    FORMAL_INTERVAL_INDICES,
    FLOAT32_DIRECTION_RELATIVE_L2_LIMIT,
    MARGIN_GATE_M,
    R6_EPSILON_MM,
    build_state_inventory,
    construct_state,
    direction_diagnostics,
    false_flags,
    generate_p1,
)
from cfd_sdf.gradients.directional_fd import direction_sha256, generate_directions
from register_fd08_v2_r6 import (
    CANONICAL_NPZ_SHA256,
    CANONICAL_PHI_FORTRAN_SHA256,
    CANONICAL_SOURCE_SURFACE_SHA256,
    CANONICAL_STATE_SHA256,
    EXPECTED_PROTECTED_DIRECTIONS,
    KERNEL_ID,
    RUNTIME,
    SOURCE_FILES,
    digest,
    load_budget_evidence,
    source_inventory,
    write_json,
)


DEFAULT_STATE = Path("/Users/sota/projects/FomulaTMU/CFD2026_09/work/sdf_native_genesis_v17/sdf_design_state.npz")
DEFAULT_R6_CRITERIA = ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_criteria.json"
DEFAULT_R6_RESULT = ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/r6_analysis.json"
DEFAULT_R6_TERMINAL = ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/terminal_verification.json"
DEFAULT_R6_DATASET = ROOT / "work/kaggle_fd08_v2_r6_dataset"
DEFAULT_DATASET = ROOT / "work/kaggle_fd08_v2_formal_dataset"
DEFAULT_CRITERIA = ROOT / "docs/evidence/fd08_v2_formal_2026_10_06/formal_criteria.json"
DEFAULT_PREFLIGHT = ROOT / "docs/evidence/fd08_v2_formal_2026_10_06/formal_preflight.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verified_json(path: Path) -> tuple[dict[str, Any], str]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file() or sidecar.read_text().strip() != digest(path):
        raise ValueError(f"missing/mismatched immutable evidence and sidecar: {path}")
    return json.loads(path.read_text()), digest(path)


def read_r6_parent(r6_criteria_path: Path, r6_result_path: Path,
                   r6_terminal_path: Path, r6_dataset_dir: Path):
    r6_criteria, criteria_sha = verified_json(r6_criteria_path)
    r6_result, result_sha = verified_json(r6_result_path)
    terminal, terminal_sha = verified_json(r6_terminal_path)
    require(r6_criteria.get("kind") == "fd08_v2_r6_calibration"
            and r6_criteria.get("immutable") is True
            and r6_criteria.get("registered_before_computation") is True,
            "formal requires immutable R6 criteria")
    require(r6_result.get("kind") == "fd08_v2_r6_analysis"
            and r6_result.get("verdict") == "PASS"
            and r6_result.get("series_count") == 8
            and r6_result.get("analysis_runs") == 1,
            "formal registration is allowed only after exact 8/8 R6 PASS analysis")
    require(terminal.get("kind") == "fd08_v2_r6_host_terminal_verification"
            and terminal.get("status") == "PASS_TERMINAL_INTEGRITY"
            and terminal.get("state_count") == 49 and terminal.get("unexpected_state_count") == 0,
            "R6 terminal integrity is not complete 49/49")
    require(r6_result.get("criteria_sha256") == criteria_sha
            and terminal.get("criteria_sha256") == criteria_sha
            and r6_result.get("terminal_verification_sha256") == terminal_sha
            and r6_criteria.get("source_commit") == terminal.get("source_commit"),
            "R6 criteria/result/terminal source chain mismatch")
    expected_dataset = dict(r6_criteria["dataset_files"])
    for name, expected in expected_dataset.items():
        path = r6_dataset_dir / name
        require(path.is_file() and digest(path) == expected, f"R6 dataset source hash mismatch: {name}")
    raw_states = {}
    for row in r6_criteria["state_inventory"]:
        raw = (r6_dataset_dir / row["phi_raw_file"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == row["phi_fortran_order_sha256"],
                f"R6 calibration state input mismatch: {row['name']}")
        raw_states.add(raw)
    require(len(raw_states) == 49, "R6 phi byte inventory is not unique")
    return r6_criteria, r6_result, terminal, criteria_sha, result_sha, terminal_sha, raw_states


def load_canonical(path: Path) -> tuple[SDFDesignState, bytes]:
    blob = path.read_bytes()
    require(hashlib.sha256(blob).hexdigest() == CANONICAL_NPZ_SHA256, "canonical NPZ hash mismatch")
    state = SDFDesignState.load(path)
    require(state.state_sha256 == CANONICAL_STATE_SHA256
            and state.source_sha256 == CANONICAL_SOURCE_SURFACE_SHA256,
            "canonical state identity mismatch")
    require(direction_sha256(generate_directions(state)["D0_interface_offset"]).startswith("8b5773b7"),
            "protected direction regeneration failed")
    require(hashlib.sha256(np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")).hexdigest()
            == CANONICAL_PHI_FORTRAN_SHA256, "canonical phi bytes mismatch")
    return state, blob


def build_formal(args: argparse.Namespace):
    r6, r6_result, r6_terminal, r6_criteria_sha, r6_result_sha, r6_terminal_sha, calibration_bytes = read_r6_parent(
        args.r6_criteria, args.r6_result, args.r6_terminal, args.r6_dataset_dir
    )
    if args.criteria.exists() or args.criteria.with_suffix(args.criteria.suffix + ".sha256").exists():
        raise FileExistsError(f"refusing to overwrite formal criteria: {args.criteria}")
    if args.dataset_dir.exists() and any(args.dataset_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite formal dataset staging: {args.dataset_dir}")
    state, baseline_npz = load_canonical(args.state)
    directions3 = generate_directions(state)
    for name, expected in EXPECTED_PROTECTED_DIRECTIONS.items():
        require(direction_sha256(directions3[name]) == expected, f"protected direction drift: {name}")
    p1, p1_audit = generate_p1(state)
    directions = {**directions3, "P1_upstream_lobe": p1}
    diag = direction_diagnostics(state, directions)
    require({name: row["sha256"] for name, row in diag["directions"].items()}
            == r6["direction_inventory"]["hashes"], "formal direction inventory differs from R6")
    formal_values = tuple(r6["formal_preregistration_template"]["epsilon_mm"])
    require(formal_values == FORMAL_EPSILON_MM, "formal epsilon values changed from pre-result rule")
    inventory, raw, audits = build_state_inventory(
        state, directions, formal_values, expected_state_count=25
    )
    for row in inventory:
        if row["kind"] == "calibration":
            row["kind"] = "formal"
    signed_formal = [row for row in inventory if row["kind"] == "formal"]
    require(len(signed_formal) == 24, "formal run must have exactly 24 signed perturbations")
    formal_signed_bytes = {raw[row["phi_raw_file"]] for row in signed_formal}
    require(len(formal_signed_bytes) == 24, "formal signed phi arrays are not pairwise byte-disjoint")
    require(not (formal_signed_bytes & calibration_bytes),
            "formal signed Float32 phi bytes collide with calibration/baseline bytes")
    require(raw["baseline_v17.phi.f32f"] in calibration_bytes,
            "formal baseline is not byte-identical to canonical calibration baseline")

    args.dataset_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes] = {"baseline_v17.sdf_design_state.npz": baseline_npz}
    for row in inventory:
        raw_name = row["phi_raw_file"]
        files[raw_name] = raw[raw_name]
        if row["kind"] == "baseline":
            row["npz_file"] = "baseline_v17.sdf_design_state.npz"
            row["npz_sha256"] = hashlib.sha256(baseline_npz).hexdigest()
        else:
            child, _ = construct_state(state, directions[row["direction_id"]], row["epsilon_mm"], row["sign"])
            npz_name = f"{row['name']}.sdf_design_state.npz"
            with tempfile.TemporaryDirectory(prefix="fd08-v2-formal-") as temp:
                npz_path = Path(temp) / npz_name
                child.save(npz_path)
                npz_bytes = npz_path.read_bytes()
            row["npz_file"] = npz_name
            row["npz_sha256"] = hashlib.sha256(npz_bytes).hexdigest()
            files[npz_name] = npz_bytes

    budget, budget_sha = load_budget_evidence(args.budget_evidence, "formal", 3300, 5600)
    files["kaggle_budget_preflight.json"] = args.budget_evidence.read_bytes()

    series_fits = {}
    for row in r6_result["series"]:
        key = f"{row['direction_id']}|{row['response']}"
        fit = row["model_a"]
        require(fit.get("available") is True, f"R6 full Model A fit unavailable: {key}")
        series_fits[key] = {
            "direction_id": row["direction_id"],
            "response": row["response"],
            "epsilon_mm": row["epsilon_mm"],
            "beta_mm": fit["beta"],
            "covariance_mm": fit["covariance"],
            "g_n_per_m": fit["g_n_per_m"],
            "se_g_n_per_m": fit["se_g_n_per_m"],
            "calibration_series_verdict": row["verdict"],
        }
    contract = {
        "schema_version": 1,
        "kind": "fd08_v2_formal_validation",
        "evidence_class": "predict_then_run_deterministic_interior_interpolation_validation",
        "criteria_id": "FD08-V2-FORMAL-2026-10-06",
        "kernel_id": KERNEL_ID,
        "input_dataset_id": "ramhachi888/cfd-opt-sdf-fd08-v2-r6",
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "source_commit": r6["source_commit"],
        "candidate_c_identity": load_candidate_c_identity(ROOT),
        "canonical_state": r6["canonical_state"],
        "calibration_binding": {
            "criteria_sha256": r6_criteria_sha,
            "result_sha256": r6_result_sha,
            "terminal_verification_sha256": r6_terminal_sha,
            "analysis_runs": 1,
            "verdict": "PASS",
            "source_commit": r6["source_commit"],
            "T2_parameters": r6["numeric_contract"]["parameters"],
            "T2_parameter_sha256": r6["numeric_contract"]["T2_parameter_sha256"],
            "model": "A",
            "fits": series_fits,
        },
        "direction_inventory": {
            "directions": DIRECTION_IDS,
            "hashes": {key: row["sha256"] for key, row in diag["directions"].items()},
            "P1_generation": p1_audit,
        },
        "formal_epsilon": {
            "source": "pre-R6 frozen R6 criteria formal_preregistration_template",
            "interval_indices": list(FORMAL_INTERVAL_INDICES),
            "formula": "sqrt(e_i*e_(i+1))",
            "epsilon_mm": list(formal_values),
            "epsilon_m": [value / 1000.0 for value in formal_values],
        },
        "geometry": r6["geometry_reject_gates"],
        "state_inventory": inventory,
        "expected_state_count": 25,
        "float32_centered_direction_audits": audits,
        "byte_disjointness": {
            "formal_signed_count": 24,
            "calibration_phi_arrays_checked": len(calibration_bytes),
            "formal_signed_arrays_pairwise_disjoint": True,
            "formal_signed_disjoint_from_all_calibration_and_baseline": True,
            "baseline_is_expected_same_canonical_state": True,
            "replacement_epsilon_search_permitted": False,
        },
        "numeric_prediction_rule": {
            "model": "frozen R6 full six-point Model A only",
            "no_refit": True,
            "x": "(epsilon_mm, epsilon_mm^3)",
            "S_pred": "x.T @ beta_mm",
            "sigma_pred_squared": "sigma0_n^2+(rho*S_pred)^2+x.T @ covariance_mm @ x",
            "observation": "(host_recomputed R(+epsilon)-R(-epsilon))/2 in N",
            "nonzero_same_sign_required": True,
            "magnitude_rule": "both absolute predicted and observed responses >= k_mag*sigma0_n",
            "acceptance_bound": "abs(S_obs-S_pred)<=max(3*sigma_pred,tol_hold*abs(S_pred))",
            "failure": "finite sign or prediction-error violation is FAIL",
            "unresolved": "insufficient magnitude, unavailable bound, or unresolvable integrity/margin condition",
        },
        "measurement": {
            **r6["measurement"],
            "solver_wall_time_cap_s": 3300,
            "kernel_execution_allowance_s": 5600,
            "per_state_timeout_s": 1500,
        },
        "budget_feasibility": {
            "evidence_sha256": budget_sha,
            "captured_utc": budget["captured_utc"],
            "cli_version": budget["cli_version"],
            "gpu_quota_remaining_hours": budget["gpu_quota_remaining_hours"],
            "platform_max_cpu_gpu_session_seconds": budget["platform_max_cpu_gpu_session_seconds"],
            "requested_kernel_execution_allowance_s": 5600,
            "status": budget["status"],
        },
        "runtime": RUNTIME,
        "dataset_files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "dataset_manifest_file": "fd08_v2_dataset_manifest.json",
        "artifact_paths": {
            "criteria": "criteria.json",
            "output_root": "fd08_v2_formal",
            "result": "fd08_v2_formal/result.json",
            "sha_manifest": "fd08_v2_formal/sha256.json",
            "terminal_marker": "fd08_v2_formal/DONE",
        },
        "source_inputs": source_inventory(),
        "decision_tree": {
            "comparison_count": 24,
            "all_24_pass": "formal PASS",
            "one_or_more_fail": "formal FAIL",
            "no_fail_and_one_or_more_unresolved": "formal UNRESOLVED",
            "no_refit_or_model_switch": True,
        },
        "qualification_flags": false_flags(),
        "not_claimed": [
            "independent noise validation", "extrapolation", "direction generalization", "grid independence",
            "physical truth", "epsilon-to-zero exact derivative", "joint 95% confidence",
            "full-field gradient/reverse/optimizer/topology qualification",
        ],
    }
    preflight = {
        "kind": "fd08_v2_formal_solver_free_preflight",
        "status": "PASS_PRE_REGISTRATION_GATES",
        "criteria_source_sha256": r6_criteria_sha,
        "calibration_result_sha256": r6_result_sha,
        "state_count": len(inventory),
        "formal_signed_count": len(signed_formal),
        "epsilon_mm": list(formal_values),
        "signed_byte_disjointness_passed": True,
        "direction_hashes": contract["direction_inventory"]["hashes"],
        "float32_centered_direction_audits": audits,
        "state_inventory": inventory,
    }
    if args.preflight.exists() or args.criteria.exists():
        raise FileExistsError("refusing to overwrite formal preflight/criteria")
    args.preflight.parent.mkdir(parents=True, exist_ok=True)
    args.preflight.write_text(json.dumps(preflight, sort_keys=True, indent=2, allow_nan=False) + "\n")
    contract["preflight"] = {"path": args.preflight.relative_to(ROOT).as_posix(), "sha256": digest(args.preflight)}
    criteria_blob = json.dumps(contract, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    criteria_sha = hashlib.sha256(criteria_blob).hexdigest()
    files["criteria.json"] = criteria_blob
    files["criteria.json.sha256"] = (criteria_sha + "\n").encode()
    dataset_manifest = {
        "kind": "fd08_v2_formal_private_dataset_manifest",
        "criteria_sha256": criteria_sha,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    files["fd08_v2_dataset_manifest.json"] = json.dumps(
        dataset_manifest, sort_keys=True, indent=2, allow_nan=False
    ).encode() + b"\n"
    args.criteria.parent.mkdir(parents=True, exist_ok=True)
    args.criteria.write_bytes(criteria_blob)
    args.criteria.with_suffix(args.criteria.suffix + ".sha256").write_text(criteria_sha + "\n")
    args.dataset_dir.mkdir(parents=True, exist_ok=True)
    for name, blob in files.items():
        path = args.dataset_dir / name
        if path.exists():
            raise FileExistsError(f"refusing to overwrite formal dataset input: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    write_json(args.dataset_dir / "dataset-metadata.json", {
        "title": "CFD Opt SDF FD08 V2 Private Inputs",
        "id": "ramhachi888/cfd-opt-sdf-fd08-v2-r6",
        "licenses": [{"name": "other"}],
    })
    print(json.dumps({"criteria_sha256": criteria_sha, "source_commit": contract["source_commit"],
                      "state_count": len(inventory), "formal_signed_count": len(signed_formal),
                      "epsilon_mm": list(formal_values), "byte_disjointness": True},
                     sort_keys=True, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--r6-criteria", type=Path, default=DEFAULT_R6_CRITERIA)
    parser.add_argument("--r6-result", type=Path, default=DEFAULT_R6_RESULT)
    parser.add_argument("--r6-terminal", type=Path, default=DEFAULT_R6_TERMINAL)
    parser.add_argument("--r6-dataset-dir", type=Path, default=DEFAULT_R6_DATASET)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    parser.add_argument("--budget-evidence", type=Path, required=True)
    return build_formal(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
