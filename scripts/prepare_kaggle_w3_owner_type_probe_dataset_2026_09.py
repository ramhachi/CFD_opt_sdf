"""Stage the immutable W3 owner-type probe criteria for a private Kaggle input."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage(criteria_path: Path, output_dir: Path) -> dict:
    sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not criteria_path.is_file() or not sidecar.is_file():
        raise ValueError("criteria JSON and SHA sidecar are required")
    digest = sha256(criteria_path)
    if sidecar.read_text().strip() != digest:
        raise ValueError("criteria SHA sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("immutable") is not True or criteria.get("registered_before_computation") is not True:
        raise ValueError("criteria are not preregistered")
    dataset_id = criteria.get("criteria_dataset_id")
    if not isinstance(dataset_id, str):
        raise ValueError("criteria dataset identity missing")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty dataset staging directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "w3_owner_type_probe_criteria.json"
    target_sidecar = target.with_suffix(target.suffix + ".sha256")
    shutil.copyfile(criteria_path, target)
    shutil.copyfile(sidecar, target_sidecar)
    (output_dir / "dataset-metadata.json").write_text(json.dumps({
        "id": dataset_id,
        "title": "CFD Opt SDF W3 Owner Type Probe Criteria " + str(criteria.get("round", 1)),
        "licenses": [{"name": "other"}],
    }, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 1,
        "kind": "private_kaggle_diagnostic_criteria_dataset",
        "dataset_id": dataset_id,
        "criteria_sha256": digest,
        "files": {name: sha256(output_dir / name) for name in (
            target.name, target_sidecar.name)},
    }
    (output_dir / "w3_owner_type_probe_dataset_manifest.json").write_text(
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
