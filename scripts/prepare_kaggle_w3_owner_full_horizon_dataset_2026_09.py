"""Stage immutable owner-horizon criteria and verified type evidence for Kaggle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_TITLE = "W3 Owner Full Horizon Diagnostic"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_copy(source: Path, target: Path, expected_sha: str) -> None:
    if not source.is_file() or sha256(source) != expected_sha:
        raise ValueError(f"source SHA mismatch: {source}")
    shutil.copyfile(source, target)
    if sha256(target) != expected_sha:
        raise ValueError(f"copied SHA mismatch: {target}")


def stage(criteria_path: Path, output_dir: Path) -> dict:
    criteria_path = Path(criteria_path)
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not criteria_path.is_file() or not sidecar.is_file():
        raise ValueError("criteria JSON and SHA sidecar are required")
    criteria_sha = sha256(criteria_path)
    if sidecar.read_text().strip() != criteria_sha:
        raise ValueError("criteria sidecar content mismatch")
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("immutable") is not True or criteria.get("registered_before_computation") is not True:
        raise ValueError("criteria must be immutable and preregistered")
    dataset_id = criteria.get("criteria_dataset_id")
    if not isinstance(dataset_id, str):
        raise ValueError("criteria dataset id is missing")
    prerequisite = criteria["type_probe_prerequisite"]
    result_path = ROOT / prerequisite["result_path"]
    result_sidecar = result_path.with_suffix(result_path.suffix + ".sha256")
    type_criteria_path = ROOT / prerequisite["criteria_path"]
    type_criteria_sidecar = type_criteria_path.with_suffix(type_criteria_path.suffix + ".sha256")
    if result_sidecar.read_text().strip() != prerequisite["result_sha256"]:
        raise ValueError("type probe result sidecar content mismatch")
    if type_criteria_sidecar.read_text().strip() != prerequisite["criteria_sha256"]:
        raise ValueError("type probe criteria sidecar content mismatch")
    result = json.loads(result_path.read_text())
    if result.get("host_verification_passed") is not True or result.get("exact_kernel_ref") != prerequisite["exact_kernel_ref"]:
        raise ValueError("type probe prerequisite is not the registered host-verified run")
    if result.get("criteria_sha256") != prerequisite["criteria_sha256"]:
        raise ValueError("type probe result does not bind the criteria round")

    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty dataset directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "w3_owner_full_horizon_criteria.json": (criteria_path, criteria_sha),
        "w3_owner_full_horizon_criteria.json.sha256": (sidecar, sha256(sidecar)),
        "w3_owner_type_probe_result.json": (result_path, prerequisite["result_sha256"]),
        "w3_owner_type_probe_result.json.sha256": (result_sidecar, prerequisite["result_sidecar_sha256"]),
        "w3_owner_type_probe_criteria.json": (type_criteria_path, prerequisite["criteria_sha256"]),
        "w3_owner_type_probe_criteria.json.sha256": (type_criteria_sidecar, prerequisite["criteria_sidecar_sha256"]),
    }
    for name, (source, digest) in files.items():
        checked_copy(source, output_dir / name, digest)
    (output_dir / "dataset-metadata.json").write_text(json.dumps({
        "id": dataset_id,
        "title": DATASET_TITLE,
        "licenses": [{"name": "other"}],
    }, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 1,
        "kind": "private_kaggle_diagnostic_criteria_and_prerequisite_dataset",
        "dataset_id": dataset_id,
        "criteria_sha256": criteria_sha,
        "type_probe_result_sha256": prerequisite["result_sha256"],
        "files": {name: sha256(output_dir / name) for name in files},
    }
    (output_dir / "w3_owner_full_horizon_dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("criteria", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.criteria, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
