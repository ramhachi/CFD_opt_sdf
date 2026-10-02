#!/usr/bin/env python3
"""Verify W3-C outputs with the unchanged v17 numerical gate evaluator."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.candidate_c_identity import load_candidate_c_identity

SPEC = importlib.util.spec_from_file_location("verify_w3_v17_legacy", ROOT / "scripts/verify_kaggle_w3_v16.py")
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)
FLAGS = {key: False for key in (
    "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}
DEFAULT_CRITERIA = ROOT / "docs/evidence/kaggle_w3_v17_candidate_c_criteria_2026_10.json"
DEFAULT_DATASET = ROOT / "work/kaggle_w3_v17_candidate_c_dataset"


def literal_false_flags(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == set(FLAGS)
            and all(value[key] is False for key in FLAGS))


def expected_remote_inventory(criteria: dict, dataset_dir: Path, criteria_sha: str) -> dict[str, str]:
    """Return Kaggle's uploaded payload only; dataset-metadata is CLI config."""
    dataset_dir = Path(dataset_dir)
    label = criteria["geometry"]["state_label"]
    manifest_path = dataset_dir / f"w3_{label}_dataset_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("W3-C staged dataset manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    required = {
        "sdf_design_state.npz": criteria["inputs"]["canonical_state_npz"]["sha256"],
        criteria["inputs"]["canonical_phi_fortran_raw"]["path"]:
            criteria["inputs"]["canonical_phi_fortran_raw"]["sha256"],
        f"w3_{label}_criteria.json": criteria_sha,
        f"w3_{label}_criteria.json.sha256": None,
    }
    criteria_sidecar = dataset_dir / f"w3_{label}_criteria.json.sha256"
    if (manifest.get("dataset_id") != criteria["input_dataset_id"]
            or manifest.get("criteria_sha256") != criteria_sha
            or not criteria_sidecar.is_file()
            or criteria_sidecar.read_text().strip() != criteria_sha):
        raise ValueError("W3-C staged dataset manifest identity mismatch")
    required[f"w3_{label}_criteria.json.sha256"] = legacy.sha256(criteria_sidecar)
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(required):
        raise ValueError("W3-C staged dataset manifest payload inventory mismatch")
    for name, expected_sha in required.items():
        if (not isinstance(name, str) or Path(name).name != name
                or not isinstance(files[name], str) or len(files[name]) != 64):
            raise ValueError("W3-C staged dataset manifest contains an invalid payload entry")
        if files[name] != expected_sha:
            raise ValueError(f"W3-C manifest payload hash differs from criteria: {name}")
        target = dataset_dir / name
        if not target.is_file() or legacy.sha256(target) != expected_sha:
            raise ValueError(f"W3-C staged payload does not match its manifest: {name}")
    expected = dict(files)
    expected[manifest_path.name] = legacy.sha256(manifest_path)
    # dataset-metadata.json is upload configuration, not a Kaggle dataset payload.
    allowed_local = set(expected) | {"dataset-metadata.json"}
    if {path.name for path in dataset_dir.iterdir()} != allowed_local:
        raise ValueError("W3-C staging directory has missing or extra files")
    return expected


def verify(download: Path, *, criteria_path=DEFAULT_CRITERIA, dataset_dir=DEFAULT_DATASET,
           kernel_version: int, kernel_id: str, dataset_version: int,
           remote_inventory_path: Path, terminal_status: str,
           terminal_log_path: Path, execution_log_path: Path, **kwargs) -> dict:
    criteria, _ = legacy.load_criteria(Path(criteria_path))
    if (criteria.get("kernel_id") != "ramhachi888/cfd-opt-sdf-w3-v17-candidate-c"
            or criteria.get("input_dataset_id") != "ramhachi888/cfd-opt-sdf-v17-candidate-c"
            or criteria.get("geometry", {}).get("state_label") != "v17_candidate_c"):
        raise ValueError("W3-C criteria kernel, dataset or state identity mismatch")
    metadata_path = ROOT / criteria["inputs"]["kernel_metadata"]["path"]
    metadata = json.loads(metadata_path.read_text())
    if (metadata.get("id") != criteria["kernel_id"]
            or metadata.get("title") != "CFD Opt SDF W3 v17 Candidate C"
            or metadata.get("is_private") is not True
            or metadata.get("dataset_sources") != [criteria["input_dataset_id"]]):
        raise ValueError("W3-C Kaggle kernel metadata identity mismatch")
    if (isinstance(kernel_version, bool) or not isinstance(kernel_version, int) or kernel_version < 1
            or isinstance(dataset_version, bool) or not isinstance(dataset_version, int) or dataset_version < 1
            or kernel_id != criteria["kernel_id"]
            or terminal_status != "KernelWorkerStatus.COMPLETE"
            or not Path(terminal_log_path).is_file()
            or Path(terminal_log_path).read_text(errors="replace").strip() != terminal_status
            or not Path(remote_inventory_path).is_file()
            or not Path(execution_log_path).is_file()
            or Path(execution_log_path).resolve() == Path(terminal_log_path).resolve()
            or Path(execution_log_path).stat().st_size == 0
            or legacy.sha256(Path(execution_log_path)) == legacy.sha256(Path(terminal_log_path))):
        raise ValueError("W3-C exact versions, distinct execution log and terminal COMPLETE evidence are required")
    dataset_dir = Path(dataset_dir)
    remote_inventory = json.loads(Path(remote_inventory_path).read_text())
    expected_inventory = expected_remote_inventory(criteria, dataset_dir, legacy.sha256(Path(criteria_path)))
    if remote_inventory != expected_inventory:
        raise ValueError("W3-C exact Kaggle dataset inventory differs from the staged input")
    frozen = load_candidate_c_identity(ROOT)
    record = json.loads((ROOT / frozen["contract_path"]).read_text())
    record_entry = criteria["inputs"]["operator_identity_record"]
    sidecar_entry = criteria["inputs"]["operator_identity_sha256"]
    sidecar_path = frozen["contract_path"] + ".sha256"
    if (criteria.get("operator") != record["operator"]
            or not literal_false_flags(criteria.get("qualification_flags"))
            or criteria.get("operator_identity_record") != {
                "path": frozen["contract_path"], "sha256": frozen["contract_sha256"]}
            or criteria.get("operator_identity_record_sha256") != frozen["contract_sha256"]
            or record_entry.get("path") != frozen["contract_path"]
            or record_entry.get("sha256") != frozen["contract_sha256"]
            or sidecar_entry.get("path") != sidecar_path
            or legacy.sha256(ROOT / sidecar_path) != sidecar_entry.get("sha256")):
        raise ValueError("W3-C criteria do not bind the parent-frozen operator identity")
    legacy.RUNNER = ROOT / criteria["inputs"]["kernel_runner"]["path"]
    legacy.HOST_VERIFIER = Path(__file__).resolve()
    result = legacy.verify(download, criteria_path=Path(criteria_path), dataset_dir=dataset_dir,
                           kernel_version=kernel_version, kaggle_log_path=execution_log_path)
    folder = Path(download) / "w3_v17_candidate_c"
    if not folder.is_dir():
        folder = Path(download)
    outcome = json.loads((folder / "outcome.json").read_text())
    if (outcome.get("candidate_c_qualification_flags") != FLAGS
            or not literal_false_flags(outcome.get("candidate_c_qualification_flags"))
            or outcome.get("operator_identity") != record["operator"]):
        raise ValueError("W3-C kernel outcome promoted a flag or drifted from the frozen operator")
    result["candidate_c_qualification_flags"] = FLAGS
    result["operator_identity_contract_sha256"] = frozen["contract_sha256"]
    result["operator_identity"] = record["operator"]
    result["canonical_state_label"] = "v17_candidate_c"
    result["host_verifier_sha256"] = legacy.sha256(Path(__file__).resolve())
    result["kernel_id"] = kernel_id
    result["dataset_version"] = dataset_version
    inventory_payload = json.dumps(remote_inventory, sort_keys=True, separators=(",", ":")) + "\n"
    result["dataset_inventory_sha256"] = hashlib.sha256(inventory_payload.encode()).hexdigest()
    result["dataset_inventory_files"] = remote_inventory
    result["terminal_status"] = terminal_status
    result["terminal_log_sha256"] = legacy.sha256(Path(terminal_log_path))
    result["execution_log_sha256"] = legacy.sha256(Path(execution_log_path))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("download", type=Path)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--kernel-version", type=int, required=True)
    parser.add_argument("--kernel-id", required=True)
    parser.add_argument("--dataset-version", type=int, required=True)
    parser.add_argument("--remote-inventory", type=Path, required=True)
    parser.add_argument("--terminal-status", required=True)
    parser.add_argument("--terminal-status-log", type=Path, required=True)
    parser.add_argument("--execution-log", type=Path, required=True)
    parser.add_argument("--result-evidence", type=Path)
    args = parser.parse_args()
    result = verify(args.download, criteria_path=args.criteria, dataset_dir=args.dataset_dir,
                    kernel_version=args.kernel_version, kernel_id=args.kernel_id,
                    dataset_version=args.dataset_version, remote_inventory_path=args.remote_inventory,
                    terminal_status=args.terminal_status, terminal_log_path=args.terminal_status_log,
                    execution_log_path=args.execution_log)
    if args.result_evidence:
        legacy.write_result_evidence(args.result_evidence, result)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
