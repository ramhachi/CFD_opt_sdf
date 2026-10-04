#!/usr/bin/env python3
"""Pre-register and stage a disjoint Candidate C FD-08 calibration dataset.

The command is intentionally write-once and requires the clean pushed
integration branch. It performs only host-side input construction and
Float32 representability checks; it does not launch a solver or Kaggle kernel.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.candidate_c_identity import load_candidate_c_identity
from cfd_sdf.fd08_calibration import (
    CALIBRATION_BASELINE_REPEATS,
    audit_float32_centered_pair,
    validate_calibration_ladder,
)
from cfd_sdf.gradients.directional_fd import (
    DIRECTION_IDS,
    direction_sha256,
    generate_directions,
    perturbed_state,
    phi_sha256,
    validate_directions,
)
from cfd_sdf.fd08_contract import (
    CANONICAL_PHI_FORTRAN_F32_SHA256,
    CANONICAL_STATE_NPZ_SHA256,
    CANONICAL_STATE_IDENTITY_SHA256,
)


BASE_CRITERIA = ROOT / "docs/evidence/xfid_candidate_c_2026_10_04/xfidc_criteria.json"
DEFAULT_STATE = ROOT / "work/sdf_native_genesis_v17/sdf_design_state.npz"
CRITERIA_OUT = ROOT / "docs/evidence/fd08_candidate_c_calibration_2026_10_04/xfidc_criteria.json"
DATASET_OUT = ROOT / "work/fd08_candidate_c_calibration_dataset"
DATASET_ID = "ramhachi888/cfd-opt-sdf-fd08-calibration"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-fd08-calibration"
KERNEL_DIR = "infra/kaggle/kernel_fd08_calibration"
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_entry(relative: str) -> dict[str, str]:
    path = ROOT / relative
    if not path.is_file():
        raise ValueError(f"registered source is missing: {relative}")
    return {"path": relative, "sha256": sha256(path), "location": "source_repo"}


def epsilon_tag(epsilon_m: float) -> str:
    return re.sub(r"[^0-9a-z]+", "_", f"{epsilon_m:.10e}".lower()).strip("_")


def _margin(phi: np.ndarray, spacing: float) -> float:
    solid = phi < 0.0
    if not solid.any():
        raise ValueError("canonical SDF contains no solid nodes")
    gaps = [np.minimum(np.arange(n), n - 1 - np.arange(n)) * spacing for n in phi.shape]
    face_gap = np.minimum(np.minimum(gaps[0][:, None, None], gaps[1][None, :, None]), gaps[2][None, None, :])
    return float(np.min(face_gap[solid] + phi[solid]))


def build(state_path: Path, epsilons_m: tuple[float, ...], source_commit: str,
          dataset_dir: Path, criteria_path: Path, *, write: bool) -> dict:
    epsilons = validate_calibration_ladder(epsilons_m)
    if len({epsilon_tag(value) for value in epsilons}) != len(epsilons):
        raise ValueError("calibration epsilon values collide in deterministic state IDs")
    base_path = BASE_CRITERIA
    base_sidecar = base_path.with_suffix(base_path.suffix + ".sha256")
    if not base_path.is_file() or base_sidecar.read_text().strip() != sha256(base_path):
        raise ValueError("the committed XFID-C criteria and sidecar must be intact")
    base = json.loads(base_path.read_text())
    frozen = load_candidate_c_identity(ROOT)
    identity_record = json.loads((ROOT / frozen["contract_path"]).read_text())
    if (base.get("operator") != identity_record["operator"]
            or base.get("operator_identity") != {
                "contract_path": frozen["contract_path"],
                "contract_sha256": frozen["contract_sha256"],
            }
            or base.get("qualification_flags") != FLAGS):
        raise ValueError("XFID-C criteria do not bind the frozen Candidate C identity and false flags")
    state_path = Path(state_path)
    if sha256(state_path) != CANONICAL_STATE_NPZ_SHA256:
        raise ValueError("canonical v17 state NPZ file SHA-256 mismatch")
    state = SDFDesignState.load(state_path)
    if state.state_sha256 != CANONICAL_STATE_IDENTITY_SHA256:
        raise ValueError("canonical v17 state identity SHA-256 mismatch")
    canonical_raw = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    if sha256_bytes(canonical_raw) != CANONICAL_PHI_FORTRAN_F32_SHA256:
        raise ValueError("canonical v17 Fortran-order Float32 phi SHA-256 mismatch")
    directions = generate_directions(state)
    direction_audit = validate_directions(state, directions)

    staged_data: dict[str, bytes] = {}
    state_order: list[dict] = []
    baseline_npz = "baseline_v17.npz"
    baseline_raw = "baseline_v17.phi_f4_fortran.raw"
    staged_data[baseline_npz] = state_path.read_bytes()
    staged_data[baseline_raw] = canonical_raw
    for index in range(CALIBRATION_BASELINE_REPEATS):
        state_order.append({
            "name": f"cal_baseline_{index + 1:02d}",
            "run_id": f"cal_baseline_{index + 1:02d}", "role": "baseline",
            "npz_file": baseline_npz, "raw_file": baseline_raw,
            "npz_sha256": sha256(state_path), "state_sha256": state.state_sha256,
            "phi_c_order_sha256": phi_sha256(state.phi, order="C"),
            "phi_fortran_sha256": sha256_bytes(canonical_raw),
            "phi_expected_margin_m": _margin(state.phi, state.spacing_m),
        })

    direction_inventory = {}
    for direction_id in DIRECTION_IDS:
        direction = directions[direction_id]
        raw = np.asarray(direction, dtype="<f4", order="C").tobytes(order="C")
        digest = sha256_bytes(raw)
        if digest != direction_sha256(direction):
            raise ValueError(f"direction bytes do not match the canonical generator: {direction_id}")
        filename = f"directions/{direction_id}.f4-c.raw"
        staged_data[filename] = raw
        direction_inventory[direction_id] = {
            "dataset_path": filename, "sha256": digest,
            "shape": list(state.shape), "dtype": "float32_little_endian", "order": "C",
        }

    perturbation_audit = []
    for direction_id in DIRECTION_IDS:
        for epsilon in epsilons:
            plus, plus_id = perturbed_state(state, directions[direction_id], epsilon_m=epsilon, sign=1)
            minus, minus_id = perturbed_state(state, directions[direction_id], epsilon_m=epsilon, sign=-1)
            direction_check = audit_float32_centered_pair(
                state.phi, directions[direction_id], epsilon_m=epsilon,
                phi_plus=plus.phi, phi_minus=minus.phi,
            )
            pair_id = f"{direction_id}__eps_{epsilon_tag(epsilon)}"
            for sign, child, identity in ((1, plus, plus_id), (-1, minus, minus_id)):
                sign_name = "plus" if sign == 1 else "minus"
                name = f"{pair_id}__{sign_name}"
                npz_rel = f"states/{name}.npz"
                raw_rel = f"states/{name}.phi_f4_fortran.raw"
                # Serialize the exact child state produced by the registered generator.
                buffer = io.BytesIO()
                np.savez_compressed(
                    buffer, phi=child.phi, design_mask=child.design_mask,
                    fixed_solid_mask=child.fixed_solid_mask,
                    forbidden_mask=child.forbidden_mask, root_mask=child.root_mask,
                    metadata=np.array(json.dumps(child.to_dict(), sort_keys=True)),
                )
                npz_bytes = buffer.getvalue()
                raw = np.asarray(child.phi, dtype="<f4", order="F").tobytes(order="F")
                staged_data[npz_rel] = npz_bytes
                staged_data[raw_rel] = raw
                state_order.append({
                    "name": name, "run_id": name, "role": "perturbation",
                    "npz_file": npz_rel, "raw_file": raw_rel,
                    "npz_sha256": sha256_bytes(npz_bytes), "state_sha256": child.state_sha256,
                    "phi_c_order_sha256": phi_sha256(child.phi, order="C"),
                    "phi_fortran_sha256": sha256_bytes(raw),
                    "phi_expected_margin_m": identity["zero_level_margin_m"],
                    "direction_id": direction_id,
                    "direction_sha256": direction_inventory[direction_id]["sha256"],
                    "epsilon_m": epsilon, "sign": sign,
                    "changed_node_count": identity["changed_node_count"],
                    "maximum_pointwise_change_m": identity["maximum_pointwise_change_m"],
                })
            perturbation_audit.append({
                "direction_id": direction_id, "epsilon_m": epsilon,
                "direction_sha256": direction_inventory[direction_id]["sha256"],
                **direction_check,
            })

    expected_count = CALIBRATION_BASELINE_REPEATS + 3 * len(epsilons) * 2
    if len(state_order) != expected_count or len({row["name"] for row in state_order}) != expected_count:
        raise ValueError("calibration run inventory is not complete and unique")
    if min(row["phi_expected_margin_m"] for row in state_order) < base["geometry"]["phi_margin_gate_m"]:
        raise ValueError("one or more registered calibration states fail the v17 SDF margin gate")

    source_inputs = copy.deepcopy(base["source_inputs"])
    for key, item in tuple(source_inputs.items()):
        source_inputs[key] = source_entry(item["path"])
    additional_sources = {
        "calibration_analysis": "src/cfd_sdf/fd08_calibration.py",
        "fd08_contract": "src/cfd_sdf/fd08_contract.py",
        "calibration_registrar": "scripts/register_fd08_calibration.py",
        "calibration_analyzer": "scripts/analyze_fd08_calibration.py",
        "cpu_rehearsal_cli": "scripts/preflight_fd08_cpu.py",
        "cpu_rehearsal_job": "scripts/waterlily_fd08_cpu_rehearsal.jl",
        "kernel_metadata": f"{KERNEL_DIR}/kernel-metadata.json",
        "kernel_wrapper": f"{KERNEL_DIR}/runner.py",
        "kernel_base_runner": f"{KERNEL_DIR}/runner_base.py",
    }
    source_inputs.update({key: source_entry(path) for key, path in additional_sources.items()})

    criteria = copy.deepcopy(base)
    criteria.update({
        "round_id": "fd08_candidate_c_calibration_2026_10_04_r1",
        "kind": "fd08_candidate_c_calibration",
        "evidence_class": "candidate_c_micro_response_calibration_not_formal_fd",
        "immutable": True, "registered_before_computation": True,
        "status": "registered_not_run", "formal_measurement_started": False,
        "registered_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "criteria_path": "docs/evidence/fd08_candidate_c_calibration_2026_10_04/xfidc_criteria.json",
        "dataset_staging_path": _repo_path(dataset_dir),
        "input_dataset_id": DATASET_ID, "kernel_id": KERNEL_ID,
        "source_inputs": source_inputs,
        "candidate_c_identity": frozen,
        "qualification_flags": FLAGS,
        "direction_generation_runtime": {
            "python_version": platform.python_version(), "numpy_version": np.__version__,
        },
        "calibration_epsilon_ladder_m": list(epsilons),
        "calibration_epsilon_ratio": epsilons[-1] / epsilons[0],
        "calibration_baseline_repeats": CALIBRATION_BASELINE_REPEATS,
        "state_order": state_order,
        "direction_inventory": direction_inventory,
        "direction_audit": direction_audit,
        "float32_direction_gate": {
            "rule": "deterministic Float32 plus/minus arrays must equal cast(phi0 +/- epsilon*d); both signs change at least one node; centered realized direction relative L2 error <= 5% on nonzero direction support",
            "relative_l2_error_limit": 0.05,
            "audit": perturbation_audit,
        },
        "response_floor_rule": {
            "rule": "per response, floor_S_N = max(max(baseline_R_N)-min(baseline_R_N), 1e-8*max(1,abs(median(baseline_R_N)))) from exactly five identical-input baseline repeats; |S| <= floor_S is UNRESOLVED",
            "baseline_repeat_count": CALIBRATION_BASELINE_REPEATS,
            "response_unit": "N",
        },
        "plateau_selection_rule": (
            "sort the preregistered calibration epsilon ladder; inspect every contiguous 5-point window; for each of the 6 direction/response series require every |S| above its independently derived floor, compute q=S/epsilon and q_ref=median(q), use normalizer=max(|q_ref|, floor_S/min(window epsilon)), require each relative deviation <=5% and all five signs identical/nonzero; select the first passing window (smallest epsilon). No common window means stop before formal registration."
        ),
        "geometry": {
            **copy.deepcopy(base["geometry"]),
            "state_label": "v17_candidate_c",
            "canonical_state_identity_sha256": CANONICAL_STATE_IDENTITY_SHA256,
            "canonical_state_npz_sha256": CANONICAL_STATE_NPZ_SHA256,
            "canonical_phi_fortran_sha256": CANONICAL_PHI_FORTRAN_F32_SHA256,
        },
        "dataset_files": {name: sha256_bytes(blob) for name, blob in staged_data.items()},
        "dataset_title": "CFD Opt SDF FD-08 Candidate C Calibration Inputs",
        "artifacts": {
            "dataset_criteria_filename": "xfidc_criteria.json",
            "dataset_manifest_filename": "fd08_calibration_dataset_manifest.json",
            "kernel_output_directory": "fd08_calibration",
            "kernel_log_filename": "kernel_log.json",
        },
        "artifact_namespaces": {
            "calibration_result_root": "docs/evidence/fd08_candidate_c_calibration_2026_10_04/result/fd08_calibration",
        },
        "calibration_formal_disjointness": {
            "calibration_run_ids": [row["name"] for row in state_order],
            "formal_run_ids": "created only by a separate post-calibration immutable registration",
            "calibration_artifacts_count_as_formal": False,
        },
        "not_claimed": ["formal FD qualification", "derivative oracle qualification", "gradient/optimizer/shape-update qualification"],
    })
    criteria["date"] = "2026-10-04"

    if write:
        if dataset_dir.exists() and any(dataset_dir.iterdir()):
            raise FileExistsError(f"refusing to overwrite nonempty dataset directory: {dataset_dir}")
        if criteria_path.exists() or criteria_path.with_suffix(criteria_path.suffix + ".sha256").exists():
            raise FileExistsError(f"refusing to overwrite immutable calibration criteria: {criteria_path}")
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
        if branch != "codex/kaggle-batch-migration":
            raise ValueError(f"registration requires codex/kaggle-batch-migration, got {branch}")
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
            raise ValueError("calibration registration requires a clean checkout")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        upstream = subprocess.check_output(["git", "rev-parse", "@{u}"], cwd=ROOT, text=True).strip()
        if source_commit != head or head != upstream:
            raise ValueError("registered source commit must be the clean pushed integration HEAD")
        dataset_dir.mkdir(parents=True, exist_ok=False)
        try:
            for name, blob in staged_data.items():
                path = dataset_dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
            payload = (json.dumps(criteria, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
            criteria_path.parent.mkdir(parents=True, exist_ok=True)
            criteria_path.write_bytes(payload)
            digest = sha256_bytes(payload)
            criteria_path.with_suffix(criteria_path.suffix + ".sha256").write_text(digest + "\n")
            (dataset_dir / "xfidc_criteria.json").write_bytes(payload)
            (dataset_dir / "xfidc_criteria.json.sha256").write_text(digest + "\n")
            (dataset_dir / "dataset-metadata.json").write_text(json.dumps({
                "title": criteria["dataset_title"], "id": DATASET_ID,
                "licenses": [{"name": "other"}],
            }, indent=2, sort_keys=True) + "\n")
        except Exception:
            # A partial preregistration must never look complete or be reused.
            if criteria_path.exists():
                criteria_path.unlink()
            criteria_path.with_suffix(criteria_path.suffix + ".sha256").unlink(missing_ok=True)
            raise
    return criteria


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--epsilon-ladder-m", type=float, nargs="+", required=True)
    parser.add_argument("--source-commit", default=None)
    parser.add_argument("--criteria", type=Path, default=CRITERIA_OUT)
    parser.add_argument("--dataset", type=Path, default=DATASET_OUT)
    parser.add_argument("--register", action="store_true", help="write immutable criteria and dataset staging")
    args = parser.parse_args()
    commit = args.source_commit or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    criteria = build(args.state, tuple(args.epsilon_ladder_m), commit, args.dataset, args.criteria, write=args.register)
    print(json.dumps({"round_id": criteria["round_id"], "runs": len(criteria["state_order"]),
                      "epsilon_ladder_m": criteria["calibration_epsilon_ladder_m"],
                      "criteria_registered": args.register,
                      "formal_qualification": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
