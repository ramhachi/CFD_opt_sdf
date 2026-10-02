#!/usr/bin/env python3
"""Print an unregistered W3-C criteria draft from the actual v17 contract."""

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

BASE = ROOT / "docs/evidence/kaggle_w3_v17_primal_criteria_2026_09.json"
OUTPUT = "docs/evidence/kaggle_w3_v17_candidate_c_criteria_2026_10.json"
DATASET_ID = "ramhachi888/cfd-opt-sdf-v17-candidate-c"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-w3-v17-candidate-c"
FLAGS = {name: False for name in (
    "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}
SOURCE_PATHS = {
    "job": "scripts/waterlily_w3_v17_candidate_c_job.jl",
    "kernel_runner": "infra/kaggle/kernel_w3_v17_candidate_c/runner.py",
    "kernel_metadata": "infra/kaggle/kernel_w3_v17_candidate_c/kernel-metadata.json",
    "dataset_preparer": "scripts/prepare_kaggle_w3_v17_candidate_c_dataset.py",
    "host_verifier": "scripts/verify_kaggle_w3_v17_candidate_c.py",
    "criteria_registrar": "scripts/prepare_kaggle_w3_v17_candidate_c_criteria.py",
    "candidate_c_body": "julia/CFDSDFWaterLily/src/CandidateCWaterLilyBody.jl",
    "normal_floor_body": "julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl",
    "operator_identity_helper": "src/cfd_sdf/candidate_c_identity.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_entry(path: str) -> dict:
    target = ROOT / path
    if not target.is_file():
        raise ValueError(f"required W3-C source is missing: {path}")
    return {"path": path, "sha256": sha256(target), "location": "source_repo"}


def build_draft() -> dict:
    identity = load_candidate_c_identity(ROOT)
    record_path = ROOT / identity["contract_path"]
    record = json.loads(record_path.read_text())
    criteria = json.loads(BASE.read_text())
    draft = copy.deepcopy(criteria)
    baseline_numerics = (copy.deepcopy(criteria["measurement"]), copy.deepcopy(criteria["backend"]),
                         copy.deepcopy(criteria["profile_adapter"]), copy.deepcopy(criteria["acceptance"]))

    draft.update({
        "criteria_id": "kaggle_w3_v17_candidate_c_2026_10",
        "criteria_round": 1,
        "kind": "waterlily_w3_candidate_c_canonical_primal_criteria",
        "status": "draft_unregistered",
        "immutable": False,
        "registered_before_computation": False,
        "input_dataset_id": DATASET_ID,
        "kernel_id": KERNEL_ID,
        "draft_source_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "criteria_source_path": BASE.relative_to(ROOT).as_posix(),
        "criteria_source_sha256": sha256(BASE),
        "round_reason": "Preparation only: preserve the v17 W3 primal criteria and bind the parent-frozen composite Candidate C operator.",
        "operator_identity_record": {"path": identity["contract_path"], "sha256": identity["contract_sha256"]},
        "operator": record["operator"],
        "operator_identity_record_sha256": identity["contract_sha256"],
        "qualification_flags": FLAGS,
    })
    draft["geometry"]["state_label"] = "v17_candidate_c"
    draft["measurement"]["force_integration_body"] = record["operator"]["force_integration_body"]
    draft["flags"].update({
        "fd_oracle_qualified": False,
        "field_gradient_qualified": False,
        "reverse_qualified": False,
        "optimizer_qualified": False,
        "topology_qualified": False,
        "shape_update_allowed": False,
    })
    inputs = draft["inputs"]
    for name, entry in list(inputs.items()):
        if entry.get("location") == "source_repo":
            entry["sha256"] = source_entry(entry["path"])["sha256"]
    for name, path in SOURCE_PATHS.items():
        inputs[name] = source_entry(path)
    inputs["operator_identity_record"] = source_entry(identity["contract_path"])
    inputs["operator_identity_sha256"] = source_entry(identity["contract_path"] + ".sha256")
    numerical_view = copy.deepcopy(draft["measurement"])
    numerical_view["force_integration_body"] = criteria["measurement"]["force_integration_body"]
    if (numerical_view, draft["backend"], draft["profile_adapter"], draft["acceptance"]) != baseline_numerics:
        raise AssertionError("W3-C preparation changed v17 numerical measurement/backend/profile/acceptance")
    return draft


if __name__ == "__main__":
    print(json.dumps(build_draft(), indent=2, sort_keys=True, allow_nan=False))
