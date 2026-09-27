"""Stage the canonical v16 SDF and immutable W3 criteria for private Kaggle."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "work/sdf_native_genesis_v16/sdf_design_state.npz"
DEFAULT_CRITERIA = ROOT / "docs/evidence/kaggle_w3_v16_primal_criteria_2026_09.json"
DEFAULT_OUT = ROOT / "work/kaggle_w3_v16_dataset"
DATASET_ID = "ramhachi888/cfd-opt-sdf-v16-genesis-state"
sys.path.insert(0, str(ROOT / "src"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(state_path: Path, criteria_path: Path, output_dir: Path) -> dict:
    from cfd_sdf.design.sdf_state import SDFDesignState

    genesis_path = ROOT / "docs/evidence/sdf_native_genesis_v16_2026_09.json"
    genesis = json.loads(genesis_path.read_text())
    expected = genesis["state"]
    if sha256(state_path) != expected["state_file_sha256"]:
        raise ValueError("canonical v16 state NPZ file hash mismatch")
    state = SDFDesignState.load(state_path)
    if state.state_sha256 != expected["state_sha256"]:
        raise ValueError("canonical v16 SDF state hash mismatch")
    if state.phi_sha256() != expected["phi_sha256"]:
        raise ValueError("canonical v16 phi hash mismatch")
    if state.source_sha256 != genesis["lineage"]["surface_stl_sha256"]:
        raise ValueError("canonical v16 state is bound to a different source surface")

    criteria_path = Path(criteria_path)
    criteria_sidecar = criteria_path.with_suffix(criteria_path.suffix + ".sha256")
    if not criteria_path.is_file() or not criteria_sidecar.is_file():
        raise ValueError("registered W3 criteria and SHA sidecar are required")
    criteria_sha = sha256(criteria_path)
    if criteria_sidecar.read_text().strip() != criteria_sha:
        raise ValueError("W3 criteria SHA sidecar mismatch")
    criteria = json.loads(criteria_path.read_text())
    if criteria.get("immutable") is not True or criteria.get("status") != "registered_not_run":
        raise ValueError("W3 criteria are not in their preregistered state")
    registered_state = criteria["inputs"]["canonical_state_npz"]
    if registered_state["sha256"] != expected["state_file_sha256"]:
        raise ValueError("W3 criteria are not bound to the canonical genesis NPZ")

    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty W3 dataset staging directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    state_target = output_dir / "sdf_design_state.npz"
    criteria_target = output_dir / "w3_v16_criteria.json"
    sidecar_target = criteria_target.with_suffix(criteria_target.suffix + ".sha256")
    shutil.copyfile(state_path, state_target)
    shutil.copyfile(criteria_path, criteria_target)
    shutil.copyfile(criteria_sidecar, sidecar_target)

    raw_target = output_dir / "canonical_v16_phi_f4_fortran.raw"
    raw_bytes = np.asarray(state.phi, dtype="<f4", order="F").tobytes(order="F")
    raw_target.write_bytes(raw_bytes)
    raw_sha = sha256(raw_target)
    if raw_sha != criteria["geometry"]["phi_fortran_sha256"]:
        raise ValueError("Fortran-order canonical phi bytes do not match W3 criteria")

    dataset_meta = {
        "title": "CFD Opt SDF v16 Genesis State",
        "id": DATASET_ID,
        "licenses": [{"name": "other"}],
    }
    (output_dir / "dataset-metadata.json").write_text(
        json.dumps(dataset_meta, indent=2, sort_keys=True) + "\n"
    )
    manifest = {
        "schema_version": 1,
        "kind": "private_kaggle_w3_v16_input_dataset",
        "dataset_id": DATASET_ID,
        "criteria_sha256": criteria_sha,
        "state_sha256": state.state_sha256,
        "state_npz_sha256": sha256(state_target),
        "phi_c_order_sha256": state.phi_sha256(),
        "phi_fortran_sha256": raw_sha,
        "files": {
            name: sha256(output_dir / name)
            for name in (
                "sdf_design_state.npz",
                "w3_v16_criteria.json",
                "w3_v16_criteria.json.sha256",
                "canonical_v16_phi_f4_fortran.raw",
            )
        },
    }
    manifest_path = output_dir / "w3_v16_dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) > 3:
        raise SystemExit("usage: prepare_kaggle_w3_dataset_2026_09.py [state.npz] [criteria.json] [out_dir]")
    state = Path(argv[0]) if len(argv) >= 1 else DEFAULT_STATE
    criteria = Path(argv[1]) if len(argv) >= 2 else DEFAULT_CRITERIA
    output = Path(argv[2]) if len(argv) >= 3 else DEFAULT_OUT
    manifest = stage(state, criteria, output)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
