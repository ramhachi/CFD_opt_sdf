#!/usr/bin/env python3
"""Stage immutable canonical, direction, and perturbed phi inputs for Kaggle."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
from pathlib import Path

import numpy as np

from cfd_sdf.design.sdf_state import SDFDesignState
from cfd_sdf.gradients.directional_fd import (
    DIRECTION_IDS,
    generate_directions,
    perturbation_case_id,
    perturbed_state,
    phi_sha256,
    validate_directions,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA = ROOT / "docs/evidence/sdf_directional_fd_v16_criteria_2026_09_round1.json"
DEFAULT_STATE = ROOT / "work/kaggle_w3_v16_dataset_registered_3c54f386/sdf_design_state.npz"
DEFAULT_OUTPUT = ROOT / "work/kaggle_sdf_directional_fd_dataset_round1"
CRITERIA_NAME = "sdf_directional_fd_v16_criteria.json"
MANIFEST_NAME = "sdf_directional_fd_v16_dataset_manifest.json"


def artifact_names(criteria: dict) -> tuple[str, str]:
    artifacts = criteria.get("artifacts", {})
    return (
        artifacts.get("dataset_criteria_filename", CRITERIA_NAME),
        artifacts.get("dataset_manifest_filename", MANIFEST_NAME),
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def stage(state_path: Path, criteria_path: Path, output_dir: Path) -> dict:
    state_path, criteria_path, output_dir = map(Path, (state_path, criteria_path, output_dir))
    criteria_sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not criteria_path.is_file() or not criteria_sidecar.is_file():
        raise ValueError("immutable criteria and sidecar must exist before dataset staging")
    criteria_sha = sha256(criteria_path)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise ValueError("criteria SHA sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    if (criteria.get("immutable") is not True
            or criteria.get("registered_before_computation") is not True
            or criteria.get("status") != "registered_not_run"
            or criteria.get("formal_measurement_started") is not False):
        raise ValueError("FD dataset requires immutable premeasurement criteria")
    generation_runtime = criteria.get("direction_generation_runtime", {})
    if (generation_runtime.get("python_version") != platform.python_version()
            or generation_runtime.get("numpy_version") != np.__version__):
        raise ValueError("dataset preparation Python/NumPy differs from direction preregistration runtime")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite a non-empty dataset stage: {output_dir}")

    state = SDFDesignState.load(state_path)
    geometry = criteria["geometry"]
    if (sha256(state_path) != geometry["canonical_state_npz_sha256"]
            or state.state_sha256 != geometry["canonical_state_sha256"]
            or list(state.shape) != geometry["point_shape"]
            or list(state.origin_m) != geometry["canonical_sdf_origin_m"]
            or state.spacing_m != geometry["design_spacing_m"]
            or state.narrow_band_width_m != geometry["narrow_band_width_m"]
            or state.source_sha256 != geometry["source_surface_sha256"]):
        raise ValueError("canonical SDF state metadata differs from the frozen FD criteria")
    canonical_f = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    if (phi_sha256(state.phi, order="C") != geometry["canonical_phi_c_order_sha256"]
            or sha256_bytes(canonical_f) != geometry["canonical_phi_fortran_sha256"]):
        raise ValueError("canonical C/F phi identity differs from the frozen FD criteria")
    dirs = generate_directions(state)
    audit = validate_directions(state, dirs)
    if audit != criteria["direction_audit"]:
        raise ValueError("host-recomputed direction identity/audit differs from criteria")

    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    state_entry = criteria["inputs"]["canonical_state_npz"]
    shutil.copyfile(state_path, output_dir / state_entry["path"])
    files[state_entry["path"]] = state_entry["sha256"]
    canonical_entry = criteria["inputs"]["canonical_phi_fortran_raw"]
    (output_dir / canonical_entry["path"]).write_bytes(canonical_f)
    files[canonical_entry["path"]] = sha256_bytes(canonical_f)

    direction_ids = tuple(criteria["direction_inventory"])
    if direction_ids != DIRECTION_IDS:
        raise ValueError("criteria direction order differs from the registered generator contract")
    for direction_id in direction_ids:
        entry = criteria["direction_inventory"][direction_id]
        raw = np.asarray(dirs[direction_id], dtype="<f4", order="C").tobytes(order="C")
        digest = sha256_bytes(raw)
        if digest != entry["sha256"]:
            raise ValueError(f"direction array SHA differs from immutable criteria: {direction_id}")
        target = output_dir / entry["dataset_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        files[entry["dataset_path"]] = digest

    perturbation_details = []
    expected_by_id = {entry["case_id"]: entry for entry in criteria["perturbation_inventory"]}
    if len(expected_by_id) != 30:
        raise ValueError("immutable criteria must contain exactly 30 perturbations")
    for item in criteria["perturbation_inventory"]:
        direction = dirs[item["direction_id"]]
        child, identity = perturbed_state(
            state, direction, epsilon_m=item["epsilon_m"], sign=item["sign"],
            margin_gate_m=item["margin_gate_m"],
        )
        raw = np.asarray(child.phi, dtype="<f4", order="F").tobytes(order="F")
        checks = {
            "state_sha256": child.state_sha256,
            "phi_file_sha256": sha256_bytes(raw),
            "phi_fortran_sha256": identity["phi_fortran_order_sha256"],
            "phi_c_order_sha256": identity["phi_c_order_sha256"],
            "maximum_pointwise_change_m": identity["maximum_pointwise_change_m"],
            "changed_node_count": identity["changed_node_count"],
            "zero_level_margin_m": identity["zero_level_margin_m"],
            "masks_unchanged": identity["masks_unchanged"],
            "outside_design_phi_identical": identity["outside_design_phi_identical"],
        }
        if any(checks[key] != item[key] for key in checks if isinstance(item[key], (str, bool, int))):
            raise ValueError(f"precomputed perturbation identity mismatch: {item['case_id']}")
        for key in ("maximum_pointwise_change_m", "zero_level_margin_m"):
            if not np.isclose(checks[key], item[key], rtol=0, atol=1e-15):
                raise ValueError(f"precomputed perturbation metric mismatch: {item['case_id']} {key}")
        target = output_dir / item["dataset_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        files[item["dataset_path"]] = sha256_bytes(raw)
        perturbation_details.append({
            "case_id": item["case_id"],
            "sign_change_node_count": int(np.count_nonzero((child.phi < 0) != (state.phi < 0))),
            "maximum_pointwise_change_m": identity["maximum_pointwise_change_m"],
            "zero_level_margin_m": identity["zero_level_margin_m"],
        })

    for name, entry in criteria["inputs"].items():
        if entry.get("location") == "kaggle_dataset" and files.get(entry["path"]) != entry["sha256"]:
            raise ValueError(f"staged dataset input is absent or hash-mismatched: {name}")

    criteria_name, manifest_name = artifact_names(criteria)
    shutil.copyfile(criteria_path, output_dir / criteria_name)
    criteria_copy_sha = sha256(output_dir / criteria_name)
    shutil.copyfile(criteria_sidecar, output_dir / f"{criteria_name}.sha256")
    files[criteria_name] = criteria_copy_sha
    files[f"{criteria_name}.sha256"] = sha256(output_dir / f"{criteria_name}.sha256")
    (output_dir / "dataset-metadata.json").write_text(json.dumps({
        "title": criteria.get("dataset_title", "CFD Opt SDF v16 Directional FD Oracle Inputs"),
        "id": criteria["input_dataset_id"],
        "licenses": [{"name": "other"}],
    }, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 1,
        "kind": "private_kaggle_sdf_directional_fd_input_dataset",
        "dataset_id": criteria["input_dataset_id"],
        "criteria_sha256": criteria_sha,
        "source_commit": criteria["source_commit"],
        "canonical_state_sha256": state.state_sha256,
        "canonical_state_npz_sha256": sha256(state_path),
        "canonical_phi_c_order_sha256": phi_sha256(state.phi, order="C"),
        "canonical_phi_fortran_sha256": sha256_bytes(canonical_f),
        "direction_audit": audit,
        "perturbation_count": len(perturbation_details),
        "perturbation_preflight": perturbation_details,
        "files": files,
    }
    (output_dir / manifest_name).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    allowed = set(files) | {"dataset-metadata.json", manifest_name}
    actual = {path.relative_to(output_dir).as_posix() for path in output_dir.rglob("*") if path.is_file()}
    if actual != allowed:
        raise ValueError(f"staged dataset inventory mismatch: extra={actual-allowed}, missing={allowed-actual}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(stage(args.state, args.criteria, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
