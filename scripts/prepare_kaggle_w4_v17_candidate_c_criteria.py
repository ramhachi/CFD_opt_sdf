#!/usr/bin/env python3
"""Print a W4-C draft only after an exact host-verified W3-C PASS exists."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cfd_sdf.candidate_c_identity import load_candidate_c_identity

BASE = ROOT / "docs/evidence/w4_v17_criteria.json"
OUTPUT = "docs/evidence/kaggle_w4_v17_candidate_c_criteria_2026_10.json"
DATASET_ID = "ramhachi888/cfd-opt-sdf-v17-w4-candidate-c"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-w4-v17-candidate-c"
W3_CRITERIA = "docs/evidence/kaggle_w3_v17_candidate_c_criteria_2026_10.json"
FLAGS = {name: False for name in (
    "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}


def literal_false_flags(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == set(FLAGS)
            and all(value[key] is False for key in FLAGS))
SOURCE_PATHS = {
    "job": "scripts/waterlily_w4_v17_candidate_c_job.jl",
    "kernel_runner": "infra/kaggle/kernel_w4_v17_candidate_c/runner.py",
    "kernel_package_runner": "infra/kaggle/kernel_w4_v17_candidate_c/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_w4_v17_candidate_c/kernel-metadata.json",
    "dataset_preparer": "scripts/prepare_kaggle_w4_v17_candidate_c_dataset.py",
    "host_verifier": "scripts/verify_kaggle_w4_v17_candidate_c.py",
    "legacy_host_evaluator": "scripts/verify_kaggle_w4_v16.py",
    "criteria_registrar": "scripts/prepare_kaggle_w4_v17_candidate_c_criteria.py",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "operator_identity_helper": "src/cfd_sdf/candidate_c_identity.py",
    "operator_identity_dependency": "src/cfd_sdf/criteria_supersession.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_entry(path: str) -> dict:
    target = ROOT / path
    if not target.is_file():
        raise ValueError(f"required W4-C source is missing: {path}")
    return {"path": path, "sha256": sha256(target), "location": "source_repo"}


def build_draft(w3_criteria_path: Path, w3_result_path: Path) -> dict:
    identity = load_candidate_c_identity(ROOT)
    record = json.loads((ROOT / identity["contract_path"]).read_text())
    w3_criteria_path, w3_result_path = Path(w3_criteria_path), Path(w3_result_path)
    w3_sidecar = w3_criteria_path.with_suffix(w3_criteria_path.suffix + ".sha256")
    w3_result_sidecar = w3_result_path.with_suffix(w3_result_path.suffix + ".sha256")
    if not all(path.is_file() for path in (w3_criteria_path, w3_sidecar,
                                             w3_result_path, w3_result_sidecar)):
        raise ValueError("W4-C preparation requires registered W3-C criteria and append-only PASS evidence")
    w3_criteria_sha, w3_result_sha = sha256(w3_criteria_path), sha256(w3_result_path)
    if (w3_sidecar.read_text().strip() != w3_criteria_sha
            or w3_result_sidecar.read_text().strip() != w3_result_sha):
        raise ValueError("W3-C criteria or PASS result sidecar mismatch")
    w3_criteria, w3_result = json.loads(w3_criteria_path.read_text()), json.loads(w3_result_path.read_text())
    if (w3_criteria.get("immutable") is not True
            or w3_criteria.get("registered_before_computation") is not True
            or w3_criteria.get("status") != "registered_not_run"
            or w3_criteria.get("geometry", {}).get("state_label") != "v17_candidate_c"
            or w3_criteria.get("kernel_id") != "ramhachi888/cfd-opt-sdf-w3-v17-candidate-c"
            or w3_criteria.get("operator") != record["operator"]
            or w3_result.get("verdict") != "PASS"
            or w3_result.get("host_verification_passed") is not True
            or w3_result.get("canonical_state_label") != "v17_candidate_c"
            or w3_result.get("criteria_sha256") != w3_criteria_sha
            or w3_result.get("kernel_id") != w3_criteria["kernel_id"]
            or w3_result.get("operator_identity") != record["operator"]
            or w3_result.get("source_commit") != w3_criteria.get("source_commit")
            or w3_result.get("backend_identity") != w3_criteria.get("backend")
            or w3_result.get("operator_identity_contract_sha256") != identity["contract_sha256"]
            or not literal_false_flags(w3_result.get("candidate_c_qualification_flags"))):
        raise ValueError("W4-C preparation requires the exact host-verified W3-C PASS on the frozen operator")

    criteria = json.loads(BASE.read_text())
    draft = copy.deepcopy(criteria)
    original_measurement = copy.deepcopy(criteria["measurement"])
    original_profile = copy.deepcopy(criteria["profile_semantics"])
    draft.update({
        "criteria_id": "waterlily_w4_v17_candidate_c_2026_10",
        "criteria_round": 1,
        "kind": "waterlily_w4_candidate_c_canonical_grid_domain_sensitivity_criteria",
        "status": "draft_unregistered",
        "immutable": False,
        "registered_before_computation": False,
        "kernel_id": KERNEL_ID,
        "input_dataset_id": DATASET_ID,
        "draft_source_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "criteria_source_path": BASE.relative_to(ROOT).as_posix(),
        "criteria_source_sha256": sha256(BASE),
        "operator": record["operator"],
        "operator_identity_record": {"path": identity["contract_path"], "sha256": identity["contract_sha256"]},
        "operator_identity_record_sha256": identity["contract_sha256"],
        "qualification_flags": FLAGS,
    })
    draft["geometry"]["state_label"] = "v17_candidate_c"
    draft["profile_semantics"]["force_integration_body"] = record["operator"]["force_integration_body"]
    draft["measurement"]["force_integration_body"] = record["operator"]["force_integration_body"]
    draft["prerequisites"]["canonical_state_identity"] = {
        "state_label": "v17_candidate_c",
        "state_sha256": w3_criteria["geometry"]["state_sha256"],
        "state_npz_sha256": w3_criteria["inputs"]["canonical_state_npz"]["sha256"],
        "phi_c_order_sha256": w3_criteria["geometry"]["phi_c_order_sha256"],
        "phi_fortran_sha256": w3_criteria["geometry"]["phi_fortran_sha256"],
        "point_shape": w3_criteria["geometry"]["point_shape"],
        "cell_shape": w3_criteria["geometry"]["cell_shape"],
        "design_lattice_spacing_m": w3_criteria["geometry"]["spacing_m"],
        "canonical_sdf_origin_m": w3_criteria["geometry"]["canonical_sdf_origin_m"],
        "source_surface_sha256": w3_criteria["geometry"]["source_surface_sha256"],
    }
    prereq = draft["prerequisites"]["w3_result_evidence"]
    prereq.update({
        "criteria_path": w3_criteria_path.relative_to(ROOT).as_posix(),
        "criteria_sha256": w3_criteria_sha,
        "path": w3_result_path.relative_to(ROOT).as_posix(),
        "sha256": w3_result_sha,
        "host_verified": True,
        "host_verifier_sha256": w3_result["host_verifier_sha256"],
        "kernel_version": w3_result["kernel_version"],
        "backend_identity": w3_result["backend_identity"],
    })
    draft["measurement"]["stationarity"]["precedent_criteria_path"] = prereq["criteria_path"]
    draft["measurement"]["stationarity"]["precedent_criteria_sha256"] = w3_criteria_sha
    inputs = draft["inputs"]
    for name, entry in list(inputs.items()):
        if entry.get("location") == "source_repo":
            entry["sha256"] = source_entry(entry["path"])["sha256"]
    for name, path in SOURCE_PATHS.items():
        inputs[name] = source_entry(path)
    inputs["operator_identity_record"] = source_entry(identity["contract_path"])
    inputs["operator_identity_sha256"] = source_entry(identity["contract_path"] + ".sha256")
    inputs["w3_criteria"] = source_entry(prereq["criteria_path"])
    inputs["w3_criteria_sha256"] = source_entry(prereq["criteria_path"] + ".sha256")
    inputs["w3_result_evidence"] = source_entry(prereq["path"])
    inputs["w3_result_sha256"] = source_entry(prereq["path"] + ".sha256")
    inputs["w3_host_verifier"] = source_entry("scripts/verify_kaggle_w3_v17_candidate_c.py")
    if draft["cases"] != criteria["cases"]:
        raise AssertionError("W4-C preparation changed the registered four-case matrix")
    measurement_view = copy.deepcopy(draft["measurement"])
    measurement_view["force_integration_body"] = original_measurement.get("force_integration_body")
    profile_view = copy.deepcopy(draft["profile_semantics"])
    profile_view["force_integration_body"] = original_profile["force_integration_body"]
    if measurement_view != original_measurement or profile_view != original_profile:
        raise AssertionError("W4-C preparation changed numerical measurement/profile gates")
    return draft


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--w3-criteria", type=Path, required=True)
    parser.add_argument("--w3-result", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_draft(args.w3_criteria, args.w3_result), indent=2,
                     sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
