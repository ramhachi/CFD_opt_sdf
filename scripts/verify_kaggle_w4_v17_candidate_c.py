#!/usr/bin/env python3
"""Verify W4-C with the unchanged v17 numerical gate evaluator."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.candidate_c_identity import load_candidate_c_identity

SPEC = importlib.util.spec_from_file_location("verify_w4_v17_legacy", ROOT / "scripts/verify_kaggle_w4_v16.py")
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)
ORIGINAL_VALIDATE_CASE_CONTRACT = legacy.validate_case_contract
FLAGS = {key: False for key in (
    "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}
DEFAULT_CRITERIA = ROOT / "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10_round2.json"
DEFAULT_DATASET = ROOT / "work/kaggle_w4_v17_candidate_c_dataset"


def literal_false_flags(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == set(FLAGS)
            and all(value[key] is False for key in FLAGS))


def load_criteria(path: Path):
    sidecar = path.with_suffix(path.suffix + ".sha256")
    legacy.require(path.is_file() and sidecar.is_file(), "W4-C criteria or SHA sidecar missing")
    digest = legacy.sha256(path)
    legacy.require(sidecar.read_text().strip() == digest, "W4-C criteria SHA mismatch")
    criteria = json.loads(path.read_text())
    legacy.require(criteria.get("immutable") is True
                   and criteria.get("registered_before_computation") is True
                   and criteria.get("status") == "registered_not_run",
                   "W4-C criteria are not immutable preregistration")
    legacy.require(criteria.get("geometry", {}).get("state_label") == "v17_candidate_c"
                   and criteria.get("kind") == "waterlily_w4_candidate_c_canonical_grid_domain_sensitivity_criteria"
                   and criteria.get("kernel_id") == "ramhachi888/cfd-opt-sdf-w4-v17-candidate-c"
                   and criteria.get("input_dataset_id") == "ramhachi888/cfd-opt-sdf-v17-w4-candidate-c",
                   "W4-C criteria identity mismatch")
    frozen = load_candidate_c_identity(ROOT)
    record = json.loads((ROOT / frozen["contract_path"]).read_text())
    record_entry = criteria["inputs"]["operator_identity_record"]
    sidecar_entry = criteria["inputs"]["operator_identity_sha256"]
    legacy.require(criteria.get("operator") == record["operator"]
                   and literal_false_flags(criteria.get("qualification_flags"))
                   and criteria.get("operator_identity_record") == {
                       "path": frozen["contract_path"], "sha256": frozen["contract_sha256"]}
                   and criteria.get("operator_identity_record_sha256") == frozen["contract_sha256"]
                   and record_entry.get("path") == frozen["contract_path"]
                   and record_entry.get("sha256") == frozen["contract_sha256"]
                   and sidecar_entry.get("path") == frozen["contract_path"] + ".sha256"
                   and legacy.sha256(ROOT / sidecar_entry["path"]) == sidecar_entry.get("sha256"),
                   "W4-C criteria do not bind the parent-frozen operator identity")
    metadata = json.loads((ROOT / criteria["inputs"]["kernel_metadata"]["path"]).read_text())
    legacy.require(metadata.get("id") == criteria["kernel_id"]
                   and metadata.get("title") == "CFD Opt SDF W4 v17 Candidate C"
                   and metadata.get("is_private") is True
                   and metadata.get("enable_gpu") is True
                   and metadata.get("machine_shape") == "NvidiaTeslaT4"
                   and metadata.get("enable_internet") is True
                   and metadata.get("dataset_sources") == [criteria["input_dataset_id"]],
                   "W4-C Kaggle kernel metadata identity mismatch")
    return criteria, digest


def validate_case_contract(criteria: dict) -> None:
    """Apply the legacy v17 contract checks on an in-memory numeric-contract view."""
    view = copy.deepcopy(criteria)
    view["geometry"]["state_label"] = "v17"
    view["kind"] = "waterlily_w4_canonical_grid_domain_sensitivity_criteria"
    view["kernel_id"] = "ramhachi888/cfd-opt-sdf-w4-v17-sensitivity"
    view["input_dataset_id"] = "ramhachi888/cfd-opt-sdf-v17-w4-sensitivity"
    view["inputs"]["kernel_metadata"]["path"] = "infra/kaggle/kernel_w4_v17/kernel-metadata.json"
    view["prerequisites"]["canonical_state_identity"]["state_label"] = "v17"
    view["profile_semantics"]["force_integration_body"] = (
        "canonical v17 candidate GridSDF only; exclude auxiliary moving-ground half-space")
    ORIGINAL_VALIDATE_CASE_CONTRACT(view)


legacy.load_criteria = load_criteria
legacy.validate_case_contract = validate_case_contract


def verify(download: Path, *, criteria_path=DEFAULT_CRITERIA, dataset_dir=DEFAULT_DATASET,
           execution_log_path: Path, **kwargs) -> dict:
    criteria, _ = load_criteria(Path(criteria_path))
    if criteria.get("prerequisites", {}).get("w3_result_evidence", {}).get("host_verified") is not True:
        raise ValueError("W4-C requires a host-verified W3-C PASS result")
    prereq = criteria["prerequisites"]["w3_result_evidence"]
    w3_criteria_path = ROOT / prereq["criteria_path"]
    w3_result_path = ROOT / prereq["path"]
    w3_criteria_sidecar = w3_criteria_path.with_suffix(w3_criteria_path.suffix + ".sha256")
    w3_result_sidecar = w3_result_path.with_suffix(w3_result_path.suffix + ".sha256")
    if (not all(path.is_file() for path in (
            w3_criteria_path, w3_result_path, w3_criteria_sidecar, w3_result_sidecar))
            or legacy.sha256(w3_criteria_path) != prereq["criteria_sha256"]
            or legacy.sha256(w3_result_path) != prereq["sha256"]
            or w3_criteria_sidecar.read_text().strip() != prereq["criteria_sha256"]
            or w3_result_sidecar.read_text().strip() != prereq["sha256"]):
        raise ValueError("W4-C exact W3-C criteria/result files or sidecars mismatch")
    w3_criteria = json.loads(w3_criteria_path.read_text())
    w3_result = json.loads(w3_result_path.read_text())
    frozen = load_candidate_c_identity(ROOT)
    if (w3_criteria.get("geometry", {}).get("state_label") != "v17_candidate_c"
            or w3_criteria.get("operator", {}).get("identity") != frozen["operator_identity"]
            or w3_result.get("verdict") != "PASS"
            or w3_result.get("host_verification_passed") is not True
            or w3_result.get("kernel_id") != "ramhachi888/cfd-opt-sdf-w3-v17-candidate-c"
            or w3_result.get("operator_identity") != json.loads(
                (ROOT / frozen["contract_path"]).read_text())["operator"]
            or w3_result.get("operator_identity_contract_sha256") != frozen["contract_sha256"]
            or not literal_false_flags(w3_result.get("candidate_c_qualification_flags"))):
        raise ValueError("W4-C prerequisite is not the exact host-verified W3-C PASS")
    version = kwargs.get("kernel_version")
    dataset_version = kwargs.get("dataset_version")
    kernel_id = kwargs.get("kernel_id")
    terminal_status = kwargs.get("terminal_status")
    terminal_log_path = kwargs.get("terminal_log_path")
    inventory_path = kwargs.get("remote_inventory_path")
    if (isinstance(version, bool) or not isinstance(version, int) or version < 1
            or isinstance(dataset_version, bool) or not isinstance(dataset_version, int) or dataset_version < 1
            or kernel_id != criteria["kernel_id"]
            or terminal_status != "KernelWorkerStatus.COMPLETE"
            or terminal_log_path is None or not Path(terminal_log_path).is_file()
            or Path(terminal_log_path).read_text(errors="replace").strip() != terminal_status
            or not Path(execution_log_path).is_file()
            or Path(execution_log_path).resolve() == Path(terminal_log_path).resolve()
            or Path(execution_log_path).stat().st_size == 0
            or legacy.sha256(Path(execution_log_path)) == legacy.sha256(Path(terminal_log_path))
            or inventory_path is None or not Path(inventory_path).is_file()):
        raise ValueError("W4-C exact versions, distinct execution log and terminal COMPLETE evidence are required")
    remote_inventory = json.loads(Path(inventory_path).read_text())
    names = legacy.dataset_names(criteria)
    dataset_root = Path(dataset_dir)
    expected_inventory = legacy.registered_dataset_files(criteria)
    expected_inventory[names["criteria"]] = legacy.sha256(Path(criteria_path))
    expected_inventory[names["criteria"] + ".sha256"] = legacy.sha256(
        dataset_root / (names["criteria"] + ".sha256"))
    expected_inventory[names["manifest"]] = legacy.sha256(dataset_root / names["manifest"])
    if remote_inventory != expected_inventory:
        raise ValueError("W4-C exact Kaggle dataset inventory differs from the immutable staged input")
    inventory_sha = legacy.remote_inventory_sha256(remote_inventory)
    kwargs["remote_inventory_sha256"] = inventory_sha
    result = legacy.verify(download, criteria_path=Path(criteria_path), dataset_dir=Path(dataset_dir), **kwargs)
    folder = Path(download) / "w4_v17_candidate_c_sensitivity"
    if not folder.is_dir():
        folder = Path(download)
    outcome = json.loads((folder / "outcome.json").read_text())
    record = json.loads((ROOT / frozen["contract_path"]).read_text())
    if (outcome.get("candidate_c_qualification_flags") != FLAGS
            or not literal_false_flags(outcome.get("candidate_c_qualification_flags"))
            or outcome.get("operator_identity") != record["operator"]):
        raise ValueError("W4-C kernel outcome promoted a flag or drifted from the frozen operator")
    result["candidate_c_qualification_flags"] = FLAGS
    result["operator_identity_contract_sha256"] = frozen["contract_sha256"]
    result["host_verifier_sha256"] = legacy.sha256(Path(__file__).resolve())
    result["dataset_inventory_sha256"] = inventory_sha
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
    parser.add_argument("--output-evidence", type=Path)
    args = parser.parse_args()
    result = verify(args.download, criteria_path=args.criteria, dataset_dir=args.dataset_dir,
                    kernel_version=args.kernel_version, kernel_id=args.kernel_id,
                    dataset_version=args.dataset_version, remote_inventory_path=args.remote_inventory,
                    terminal_status=args.terminal_status, terminal_log_path=args.terminal_status_log,
                    execution_log_path=args.execution_log)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output_evidence:
        rendered = legacy.write_append_only_evidence(args.output_evidence, result)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
