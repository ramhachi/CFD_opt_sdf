#!/usr/bin/env python3
"""Freeze the fresh-33 Candidate C FD-08 criteria after host-reviewed calibration."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import re

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.fd08_calibration import (
    audit_float32_centered_pair,
    derive_response_floor,
    recompute_force_history,
    select_formal_epsilon_ladder,
    validate_calibration_ladder,
    validate_formal_epsilon_ladder,
    verify_output_manifest,
    verify_registered_dataset,
)
from cfd_sdf.fd08_contract import validate_fd08_design
from cfd_sdf.gradients.directional_fd import (
    DIRECTION_IDS, generate_directions, perturbed_state, phi_sha256, validate_directions,
)


DEFAULT_STATE = ROOT / "work/sdf_native_genesis_v17/sdf_design_state.npz"
DEFAULT_CAL_CRITERIA = ROOT / "docs/evidence/fd08_candidate_c_calibration_2026_10_04/xfidc_criteria.json"
DEFAULT_CAL_RESULT = ROOT / "docs/evidence/fd08_candidate_c_calibration_2026_10_04/calibration_result.json"
DEFAULT_CRITERIA_OUT = ROOT / "docs/evidence/fd08_candidate_c_formal_2026_10_04/xfidc_criteria.json"
DEFAULT_DATASET_OUT = ROOT / "work/fd08_candidate_c_formal_dataset"
DATASET_ID = "ramhachi888/cfd-opt-sdf-fd08-formal"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-fd08-formal"
KERNEL_DIR = "infra/kaggle/kernel_fd08_formal"
FLAGS = {key: False for key in (
    "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _repo_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _repo_relative(path: Path) -> str:
    candidate = Path(path)
    resolved = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"calibration evidence must be committed inside the source repository: {path}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def immutable_json(path: Path) -> tuple[dict, str]:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValueError(f"immutable JSON and sidecar are required: {path}")
    digest = sha256(path)
    if sidecar.read_text().strip() != digest:
        raise ValueError(f"immutable JSON sidecar mismatch: {path}")
    return json.loads(path.read_text()), digest


def entry(relative: str) -> dict:
    path = ROOT / relative
    if not path.is_file():
        raise ValueError(f"registered source or calibration evidence is missing: {relative}")
    return {"path": relative, "sha256": sha256(path), "location": "source_repo"}


def epsilon_tag(value: float) -> str:
    return re.sub(r"[^0-9a-z]+", "_", f"{value:.10e}".lower()).strip("_")


def state_bytes(state: SDFDesignState) -> bytes:
    buffer = io.BytesIO()
    np.savez_compressed(
        buffer, phi=state.phi, design_mask=state.design_mask,
        fixed_solid_mask=state.fixed_solid_mask, forbidden_mask=state.forbidden_mask,
        root_mask=state.root_mask, metadata=np.array(json.dumps(state.to_dict(), sort_keys=True)),
    )
    return buffer.getvalue()


def build(state_path: Path, calibration_criteria_path: Path, calibration_result_path: Path,
          criteria_path: Path, dataset_dir: Path, source_commit: str, *, write: bool) -> dict:
    cal, cal_sha = immutable_json(Path(calibration_criteria_path))
    result, result_sha = immutable_json(Path(calibration_result_path))
    expected_flags = FLAGS
    if not isinstance(cal.get("dataset_staging_path"), str):
        raise ValueError("calibration criteria must bind its locally staged immutable dataset")
    if (cal.get("kind") != "fd08_candidate_c_calibration"
            or cal.get("immutable") is not True
            or cal.get("registered_before_computation") is not True
            or cal.get("status") != "registered_not_run"
            or cal.get("qualification_flags") != expected_flags
            or result.get("kind") != "fd08_candidate_c_calibration_analysis"
            or result.get("criteria_registered") is not False
            or result.get("qualification_flags") != expected_flags):
        raise ValueError("formal registration requires immutable calibration criteria and host analysis with false flags")
    cal_dataset = ROOT / cal["dataset_staging_path"]
    dataset_audit = verify_registered_dataset(cal, cal_sha, cal_dataset)
    calibration_namespace = cal.get("artifact_namespaces", {}).get("calibration_result_root")
    if (not isinstance(calibration_namespace, str)
            or Path(result.get("result_root_path", "")).resolve() != (ROOT / calibration_namespace).resolve()):
        raise ValueError("calibration raw outputs are outside their immutable registered namespace")
    result_root = Path(result.get("result_root_path", "")).resolve()
    runner_result_path = Path(result.get("runner_result_path", "")).resolve()
    manifest_audit = verify_output_manifest(result_root, runner_result_path)
    runner_terminal = json.loads(runner_result_path.read_text())
    runner_source = cal.get("source_inputs", {}).get("kernel_base_runner", {})
    if (result.get("runner_output_manifest") != manifest_audit
            or sha256(runner_result_path) != result.get("runner_result_sha256")
            or not isinstance(runner_source, dict)
            or runner_terminal.get("runner_sha256") != runner_source.get("sha256")):
        raise ValueError("calibration output manifest changed after host analysis")
    for run_id, binding in result.get("raw_force_history_inventory", {}).items():
        raw_path = (result_root / binding["path"]).resolve()
        if result_root not in raw_path.parents or sha256(raw_path) != binding.get("sha256"):
            raise ValueError(f"calibration raw force artifact changed after analysis: {run_id}")
        recomputed = recompute_force_history(
            raw_path,
            force_scale_n_per_solver_force=float(result["force_scale_n_per_solver_force"]),
        )
        if recomputed["force_n"] != binding.get("host_recomputed_force_n"):
            raise ValueError(f"calibration raw force response no longer matches saved host analysis: {run_id}")
    selection = result.get("formal_ladder_selection", {})
    if (cal.get("kind") != "fd08_candidate_c_calibration"
            or result.get("calibration_criteria_sha256") != cal_sha
            or result.get("fresh_solver_execution_verified") is not True
            or result.get("formal_qualification") is not False
            or selection.get("status") != "COMMON_PLATEAU_FOUND"
            or selection.get("registration_allowed") is not True):
        raise ValueError("a host-recomputed calibration with a common plateau is required")
    calibration_epsilons = validate_calibration_ladder(cal.get("calibration_epsilon_ladder_m", []))
    epsilons = validate_formal_epsilon_ladder(selection.get("selected_formal_epsilon_ladder_m", []))
    if len({epsilon_tag(value) for value in epsilons}) != len(epsilons):
        raise ValueError("formal epsilon values collide in deterministic state IDs")
    if not any(calibration_epsilons[start:start + len(epsilons)] == epsilons
               for start in range(len(calibration_epsilons) - len(epsilons) + 1)):
        raise ValueError("formal ladder is not a contiguous five-point window from the registered calibration ladder")
    if result.get("calibration_run_ids") != [row.get("name") for row in cal.get("state_order", [])]:
        raise ValueError("calibration result run inventory does not match its immutable criteria")
    baseline_ids = result.get("baseline_repeat_ids", [])
    raw_inventory = result.get("raw_force_history_inventory", {})
    expected_baseline_ids = [row["name"] for row in cal["state_order"] if row.get("role") == "baseline"]
    if baseline_ids != expected_baseline_ids or set(raw_inventory) != {row["name"] for row in cal["state_order"]}:
        raise ValueError("calibration analysis lacks the exact five baseline/raw-history inventory")
    floors = {
        response: derive_response_floor([
            raw_inventory[run_id]["host_recomputed_force_n"][response] for run_id in baseline_ids
        ])
        for response in ("drag", "downforce")
    }
    if floors != result.get("baseline_resolution_floors"):
        raise ValueError("calibration response floors do not recompute from the saved baseline responses")
    pair_data = result.get("direction_response_pairs", {})
    if set(pair_data) != set(DIRECTION_IDS):
        raise ValueError("calibration analysis does not contain all three direction series")
    recomputed_selection = select_formal_epsilon_ladder(
        epsilons_m=calibration_epsilons,
        pairs={direction: {
            response: pair_data[direction][response] for response in ("drag", "downforce")
        } for direction in DIRECTION_IDS},
        response_floors_n={key: value["response_floor_n"] for key, value in floors.items()},
    )
    if recomputed_selection != selection:
        raise ValueError("formal epsilon selection differs from independent recomputation of saved calibration responses")
    floors = {
        response: float(result["baseline_resolution_floors"][response]["response_floor_n"])
        for response in ("drag", "downforce")
    }
    if any(not np.isfinite(value) or value <= 0.0 for value in floors.values()):
        raise ValueError("calibration response floors must be positive finite N values")
    source_runtime = result.get("observed_runtime_identity")
    if not isinstance(source_runtime, dict) or not source_runtime.get("gpu_uuid"):
        raise ValueError("observed calibration T4 runtime/device identity is required")
    state_path = Path(state_path)
    if sha256(state_path) != cal["geometry"]["canonical_state_npz_sha256"]:
        raise ValueError("formal state NPZ SHA differs from the calibration canonical input")
    state = SDFDesignState.load(state_path)
    if state.state_sha256 != cal["geometry"]["canonical_state_identity_sha256"]:
        raise ValueError("formal state identity differs from the calibration canonical input")
    directions = generate_directions(state)
    direction_audit = validate_directions(state, directions)
    if direction_audit != cal["direction_audit"]:
        raise ValueError("formal direction lineage differs from the calibration direction hashes")

    staged: dict[str, bytes] = {}
    for direction_id in DIRECTION_IDS:
        raw_direction = np.asarray(directions[direction_id], dtype="<f4", order="C").tobytes(order="C")
        direction_record = cal["direction_inventory"][direction_id]
        if sha256_bytes(raw_direction) != direction_record["sha256"]:
            raise ValueError(f"formal direction bytes differ from the canonical calibration lineage: {direction_id}")
        staged[direction_record["dataset_path"]] = raw_direction
    baseline_raw = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    baseline_npz = state_path.read_bytes()
    staged["baseline_v17.npz"] = baseline_npz
    staged["baseline_v17.phi_f4_fortran.raw"] = baseline_raw
    state_order = []
    for index, label in enumerate(("A", "B", "C"), start=1):
        state_order.append({
            "name": f"formal_baseline_{label}",
            "run_id": f"formal_baseline_{label}", "role": "baseline",
            "npz_file": "baseline_v17.npz", "raw_file": "baseline_v17.phi_f4_fortran.raw",
            "npz_sha256": sha256_bytes(baseline_npz), "state_sha256": state.state_sha256,
            "phi_c_order_sha256": phi_sha256(state.phi, order="C"),
            "phi_fortran_sha256": sha256_bytes(baseline_raw),
            "phi_expected_margin_m": float(cal["state_order"][0]["phi_expected_margin_m"]),
        })

    for direction_id in DIRECTION_IDS:
        for epsilon in epsilons:
            plus, plus_identity = perturbed_state(state, directions[direction_id], epsilon_m=epsilon, sign=1)
            minus, minus_identity = perturbed_state(state, directions[direction_id], epsilon_m=epsilon, sign=-1)
            audit = audit_float32_centered_pair(
                state.phi, directions[direction_id], epsilon_m=epsilon,
                phi_plus=plus.phi, phi_minus=minus.phi,
                max_relative_l2_error=cal["float32_direction_gate"]["relative_l2_error_limit"],
            )
            pair = f"{direction_id}__eps_{epsilon_tag(epsilon)}"
            for sign, child, identity in ((1, plus, plus_identity), (-1, minus, minus_identity)):
                suffix = "plus" if sign == 1 else "minus"
                name = f"{pair}__{suffix}"
                npz_path, raw_path = f"states/{name}.npz", f"states/{name}.phi_f4_fortran.raw"
                npz_data = state_bytes(child)
                phi_raw = np.asarray(child.phi, dtype="<f4", order="F").tobytes(order="F")
                staged[npz_path], staged[raw_path] = npz_data, phi_raw
                state_order.append({
                    "name": name, "run_id": name, "role": "perturbation", "npz_file": npz_path,
                    "raw_file": raw_path, "npz_sha256": sha256_bytes(npz_data),
                    "state_sha256": child.state_sha256,
                    "phi_c_order_sha256": phi_sha256(child.phi, order="C"),
                    "phi_fortran_sha256": sha256_bytes(phi_raw),
                    "phi_expected_margin_m": identity["zero_level_margin_m"],
                    "direction_id": direction_id,
                    "direction_sha256": direction_audit["direction_sha256"][direction_id],
                    "epsilon_m": epsilon, "sign": sign,
                    "changed_node_count": identity["changed_node_count"],
                    "effective_direction_audit": audit,
                })
    calibration_ids = list(cal["calibration_formal_disjointness"]["calibration_run_ids"])
    design = validate_fd08_design(calibration_ids, state_order)
    if len(state_order) != 33:
        raise ValueError("formal criteria require exactly three baselines and 30 signed perturbations")
    if min(row["phi_expected_margin_m"] for row in state_order) < cal["geometry"]["phi_margin_gate_m"]:
        raise ValueError("one or more formal states fail the preregistered SDF margin gate")

    source_inputs = {key: entry(value["path"]) for key, value in cal["source_inputs"].items()}
    source_inputs.update({
        "formal_registrar": entry("scripts/register_fd08_formal.py"),
        "formal_verifier": entry("scripts/verify_fd08_formal.py"),
        "formal_kernel_metadata": entry(f"{KERNEL_DIR}/kernel-metadata.json"),
        "formal_kernel_wrapper": entry(f"{KERNEL_DIR}/runner.py"),
        "formal_kernel_base_runner": entry(f"{KERNEL_DIR}/runner_base.py"),
        "calibration_criteria": entry(_repo_relative(calibration_criteria_path)),
        "calibration_result": entry(_repo_relative(calibration_result_path)),
    })
    criteria = copy.deepcopy(cal)
    criteria.update({
        "round_id": "fd08_candidate_c_formal_2026_10_04_r1",
        "kind": "fd08_candidate_c_formal",
        "evidence_class": "candidate_c_local_centered_directional_fd_formal_qualification",
        "immutable": True, "registered_before_computation": True,
        "status": "registered_not_run", "formal_measurement_started": False,
        "registered_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "criteria_path": "docs/evidence/fd08_candidate_c_formal_2026_10_04/xfidc_criteria.json",
        "input_dataset_id": DATASET_ID, "kernel_id": KERNEL_ID,
        "dataset_staging_path": _repo_path(dataset_dir),
        "source_inputs": source_inputs,
        "state_order": state_order,
        "dataset_files": {name: sha256_bytes(data) for name, data in staged.items()},
        "calibration_evidence": {
            "criteria_path": _repo_relative(calibration_criteria_path),
            "criteria_sha256": cal_sha,
            "result_path": _repo_relative(calibration_result_path),
            "result_sha256": result_sha,
            "calibration_run_ids": calibration_ids,
            "formal_run_ids": [row["name"] for row in state_order],
            "calibration_raw_force_history_sha256": {
                key: value["sha256"] for key, value in result["raw_force_history_inventory"].items()
            },
            "registered_dataset_audit": dataset_audit,
            "runner_output_manifest": manifest_audit,
            "calibration_formal_run_id_overlap": [],
            "calibration_formal_artifact_paths_disjoint": True,
        },
        "artifact_namespaces": {
            "calibration_result_root": "docs/evidence/fd08_candidate_c_calibration_2026_10_04/result/fd08_calibration",
            "formal_result_root": "docs/evidence/fd08_candidate_c_formal_2026_10_04/result/fd08_formal",
        },
        "formal_epsilon_ladder_m": list(epsilons),
        "response_resolution_floor_n": floors,
        "observed_calibration_runtime_identity": source_runtime,
        "runtime_rule": "formal T4 must match the observed calibration Julia, WaterLily, CUDA.jl, GPU model and selected GPU UUID; driver is recorded as not gated. Runtime identity is re-observed and host-verified from formal output.",
        "formal_baseline_repeat_count": 3,
        "formal_run_count": 33,
        "formal_design_validation": design,
        "formal_gate_rule": (
            "For each direction/response, all five registered +/- pairs are mandatory. S=(R+ - R-)/2 N and q=S/epsilon N/m are recomputed from raw histories. |S| <= its frozen response floor marks that epsilon unresolved. At least three resolved points are required; signs of all resolved points must agree; plateau reference is the median q over resolved points; deviation is abs(q-q_ref)/max(abs(q_ref), floor_S/min(epsilon over resolved points)) and each resolved point must be <=5%. A resolved sign or plateau failure yields FAIL even if another epsilon is sub-floor; otherwise any sub-floor point or fewer than three resolved points yields UNRESOLVED; only all five resolved with passing gates yields PASS. Global precedence is FAIL, then UNRESOLVED, then PASS across the six combinations.",
        ),
        "artifacts": {
            "dataset_criteria_filename": "xfidc_criteria.json",
            "dataset_manifest_filename": "fd08_formal_dataset_manifest.json",
            "kernel_output_directory": "fd08_formal",
            "kernel_log_filename": "kernel_log.json",
        },
        "calibration_formal_disjointness": {
            "calibration_run_ids": calibration_ids,
            "formal_run_ids": [row["name"] for row in state_order],
            "overlap": [],
            "calibration_artifacts_used_as_formal": False,
        },
        "qualification_flags": FLAGS,
        "fresh_solver_execution_verified": False,
        "formal_qualification": False,
    })
    if write:
        if dataset_dir.exists() and any(dataset_dir.iterdir()):
            raise FileExistsError(f"refusing to overwrite nonempty formal dataset: {dataset_dir}")
        sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
        if criteria_path.exists() or sidecar.exists():
            raise FileExistsError(f"refusing to overwrite immutable formal criteria: {criteria_path}")
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
        if branch != "codex/kaggle-batch-migration":
            raise ValueError(f"formal registration requires codex/kaggle-batch-migration, got {branch}")
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
            raise ValueError("formal registration requires a clean checkout")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        upstream = subprocess.check_output(["git", "rev-parse", "@{u}"], cwd=ROOT, text=True).strip()
        if source_commit != head or head != upstream:
            raise ValueError("formal source commit must be the clean pushed integration HEAD")
        dataset_dir.mkdir(parents=True, exist_ok=False)
        try:
            for name, data in staged.items():
                path = dataset_dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            payload = (json.dumps(criteria, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
            criteria_path.parent.mkdir(parents=True, exist_ok=True)
            criteria_path.write_bytes(payload)
            digest = sha256_bytes(payload)
            sidecar.write_text(digest + "\n")
            (dataset_dir / "xfidc_criteria.json").write_bytes(payload)
            (dataset_dir / "xfidc_criteria.json.sha256").write_text(digest + "\n")
            (dataset_dir / "dataset-metadata.json").write_text(json.dumps({
                "title": "CFD Opt SDF FD-08 Candidate C Formal Fresh 33 Inputs",
                "id": DATASET_ID, "licenses": [{"name": "other"}],
            }, indent=2, sort_keys=True) + "\n")
        except Exception:
            criteria_path.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            raise
    return criteria


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--calibration-criteria", type=Path, default=DEFAULT_CAL_CRITERIA)
    parser.add_argument("--calibration-result", type=Path, default=DEFAULT_CAL_RESULT)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA_OUT)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_OUT)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    commit = args.source_commit or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    result = build(args.state, args.calibration_criteria, args.calibration_result,
                   args.criteria, args.dataset, commit, write=args.register)
    print(json.dumps({"round_id": result["round_id"], "formal_runs": len(result["state_order"]),
                      "epsilon_ladder_m": result["formal_epsilon_ladder_m"],
                      "criteria_registered": args.register, "formal_qualification": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
