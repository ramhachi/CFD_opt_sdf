#!/usr/bin/env python3
"""Stage canonical-state inputs for an immutable W4 criteria round."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from verify_kaggle_w4_v17_candidate_c import (
    load_criteria,
    legacy as _legacy_verifier,
    validate_case_contract,
)
sha256 = _legacy_verifier.sha256
verify_registered_source = _legacy_verifier.verify_registered_source
from cfd_sdf.candidate_c_identity import load_candidate_c_identity
DEFAULT_STATE = ROOT / "work/sdf_native_genesis_v17/sdf_design_state.npz"
DEFAULT_CRITERIA = ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10.json"
DEFAULT_OUTPUT = ROOT / "work/kaggle_w4_v17_candidate_c_dataset"
EXPECTED_LABEL = "v17_candidate_c"
EXPECTED_DATASET_ID = "ramhachi888/cfd-opt-sdf-v17-w4-candidate-c"


def literal_false_flags(value: object) -> bool:
    keys = {"shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology"}
    return isinstance(value, dict) and set(value) == keys and all(value[key] is False for key in keys)


def label_from_criteria(criteria: dict) -> str:
    return str(criteria["geometry"].get("state_label", "v16"))


def stage(state_path: Path, criteria_path: Path, output_dir: Path) -> dict:
    criteria_path = Path(criteria_path)
    criteria, criteria_sha = load_criteria(criteria_path)
    validate_case_contract(criteria)
    verify_registered_source(criteria)
    label = label_from_criteria(criteria)
    if label != EXPECTED_LABEL or criteria.get("input_dataset_id") != EXPECTED_DATASET_ID:
        raise ValueError("W4 Candidate C state, dataset or operator identity mismatch")
    frozen = load_candidate_c_identity(ROOT)
    record = json.loads((ROOT / frozen["contract_path"]).read_text())
    record_entry = criteria["inputs"]["operator_identity_record"]
    sidecar_entry = criteria["inputs"]["operator_identity_sha256"]
    if (criteria.get("operator") != record["operator"]
            or criteria.get("operator_identity_record") != {
                "path": frozen["contract_path"], "sha256": frozen["contract_sha256"]}
            or criteria.get("operator_identity_record_sha256") != frozen["contract_sha256"]
            or not literal_false_flags(criteria.get("qualification_flags"))
            or record_entry.get("path") != frozen["contract_path"]
            or record_entry.get("sha256") != frozen["contract_sha256"]
            or sidecar_entry.get("path") != frozen["contract_path"] + ".sha256"
            or sha256(ROOT / sidecar_entry["path"]) != sidecar_entry.get("sha256")):
        raise ValueError("W4 criteria do not bind the exact frozen Candidate C identity")
    prefix = f"w4_{label}"
    state_path = Path(state_path)
    geometry = criteria["geometry"]
    state_entry = criteria["inputs"]["canonical_state_npz"]
    raw_entry = criteria["inputs"]["canonical_phi_fortran_raw"]
    if sha256(state_path) != state_entry["sha256"]:
        raise ValueError("canonical W4 state NPZ SHA mismatch")
    with np.load(state_path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"].item()))
        phi = np.asarray(archive["phi"], dtype="<f4")
    if list(phi.shape) != geometry["point_shape"] or not np.isfinite(phi).all():
        raise ValueError("canonical W4 state point shape or finiteness mismatch")
    phi_c = hashlib.sha256(np.ascontiguousarray(phi, dtype="<f4").tobytes(order="C")).hexdigest()
    phi_f_bytes = np.asarray(phi, dtype="<f4", order="F").tobytes(order="F")
    phi_f = hashlib.sha256(phi_f_bytes).hexdigest()
    if (metadata.get("state_sha256") != geometry["canonical_state_sha256"]
            or metadata.get("source_sha256") != geometry["source_surface_sha256"]
            or metadata.get("shape") != geometry["point_shape"]
            or metadata.get("origin_m") != geometry["canonical_sdf_origin_m"]
            or metadata.get("spacing_m") != geometry["design_lattice_spacing_m"]
            or phi_c != geometry["canonical_phi_c_order_sha256"]
            or phi_f != geometry["canonical_phi_fortran_sha256"]
            or phi_f != raw_entry["sha256"]):
        raise ValueError(f"canonical W4 {label} state and criteria identities disagree")

    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty W4 dataset directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    state_target = output_dir / state_entry["path"]
    shutil.copyfile(state_path, state_target)
    criteria_target = output_dir / f"{prefix}_criteria.json"
    shutil.copyfile(criteria_path, criteria_target)
    criteria_sidecar_target = criteria_target.with_suffix(criteria_target.suffix + ".sha256")
    shutil.copyfile(criteria_path.with_suffix(criteria_path.suffix + ".sha256"),
                    criteria_sidecar_target)
    raw_target = output_dir / raw_entry["path"]
    raw_target.write_bytes(phi_f_bytes)

    metadata_target = output_dir / "dataset-metadata.json"
    metadata_target.write_text(json.dumps({
        "title": f"CFD Opt SDF W4 {label} Sensitivity Inputs",
        "id": criteria["input_dataset_id"],
        "licenses": [{"name": "other"}],
    }, indent=2, sort_keys=True) + "\n")
    files = {
        entry["path"]: entry["sha256"]
        for entry in criteria["inputs"].values()
        if entry.get("location") == "kaggle_dataset"
    }
    files.update({
        f"{prefix}_criteria.json": criteria_sha,
        f"{prefix}_criteria.json.sha256": sha256(criteria_sidecar_target),
    })
    if set(files) != {state_entry["path"], raw_entry["path"],
                      f"{prefix}_criteria.json", f"{prefix}_criteria.json.sha256"}:
        raise ValueError(f"W4 {label} criteria dataset inputs do not match the staging contract")
    for name, expected in files.items():
        if sha256(output_dir / name) != expected:
            raise ValueError(f"staged W4 input hash mismatch: {name}")
    manifest = {
        "schema_version": 1,
        "kind": f"private_kaggle_w4_{label}_sensitivity_input_dataset",
        "dataset_id": criteria["input_dataset_id"],
        "canonical_state_label": label,
        "criteria_sha256": criteria_sha,
        "state_sha256": geometry["canonical_state_sha256"],
        "state_npz_sha256": sha256(state_target),
        "phi_c_order_sha256": phi_c,
        "phi_fortran_sha256": phi_f,
        "point_shape": geometry["point_shape"],
        "cell_shape": geometry["cell_shape"],
        "design_lattice_spacing_m": geometry["design_lattice_spacing_m"],
        "files": files,
    }
    manifest_path = output_dir / f"{prefix}_dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = stage(args.state, args.criteria, args.output)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
