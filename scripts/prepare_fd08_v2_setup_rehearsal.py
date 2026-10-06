#!/usr/bin/env python3
"""Prepare a two-state Kaggle setup-only rehearsal; no R6 criteria are registered."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from register_fd08_v2_r6 import RUNTIME, load_budget_evidence, source_inventory, write_json


DEFAULT_FULL_DATASET = ROOT / "work/kaggle_fd08_v2_r6_dataset"
DEFAULT_DATASET = ROOT / "work/kaggle_fd08_v2_setup_dataset"
DEFAULT_PREFLIGHT = ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/preflight.json"
DEFAULT_CRITERIA = ROOT / "docs/evidence/fd08_v2_r6_2026_10_06/setup_rehearsal_criteria.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--full-dataset", type=Path, default=DEFAULT_FULL_DATASET)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    parser.add_argument("--criteria", type=Path, default=DEFAULT_CRITERIA)
    parser.add_argument("--budget-evidence", type=Path, required=True)
    args = parser.parse_args()
    if len(args.source_commit) != 40 or subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip() != args.source_commit:
        raise ValueError("setup source commit must equal this clean, integrated checkout HEAD")
    if not args.preflight.is_file() or not args.full_dataset.is_dir():
        raise FileNotFoundError("R6 preflight and state dataset must exist before setup preparation")
    if args.dataset_dir.exists() and any(args.dataset_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite setup dataset: {args.dataset_dir}")
    if args.criteria.exists() or args.criteria.with_suffix(args.criteria.suffix + ".sha256").exists():
        raise FileExistsError(f"refusing to overwrite setup-only criteria: {args.criteria}")
    budget, budget_sha = load_budget_evidence(args.budget_evidence, "setup", 0, 7200)
    preflight = json.loads(args.preflight.read_text())
    states = preflight["state_order"]
    chosen = [next(row for row in states if row["kind"] == "baseline")]
    epsilon = preflight["epsilon_ladder_mm"][0]
    p1name = f"P1_upstream_lobe__e{epsilon:.17g}mm__plus"
    chosen.append(next(row for row in states if row["name"] == p1name))
    args.dataset_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for row in chosen:
        for key in ("phi_raw_file", "npz_file"):
            name = row[key]
            path = args.full_dataset / name
            data = path.read_bytes()
            expected_hash = row["npz_sha256"] if key == "npz_file" else row["phi_fortran_order_sha256"]
            if hashlib.sha256(data).hexdigest() != expected_hash:
                raise ValueError(f"setup input hash mismatch: {name}")
            files[name] = data
            (args.dataset_dir / name).write_bytes(data)
    files["kaggle_budget_preflight.json"] = args.budget_evidence.read_bytes()
    criteria = {
        "schema_version": 1,
        "kind": "fd08_v2_setup_rehearsal",
        "immutable": True,
        "evidence_class": "setup_only_not_calibration_or_formal",
        "source_commit": args.source_commit,
        "kernel_id": "ramhachi888/cfd-opt-sdf-fd08-v2-r6",
        "input_dataset_id": "ramhachi888/cfd-opt-sdf-fd08-v2-r6",
        "runtime": RUNTIME,
        "canonical_state": preflight["canonical"],
        "state_inventory": chosen,
        "expected_state_count": 2,
        "per_state_timeout_s": 900,
        "time_limit_scope": "bounded single setup step; not scientific solver wall time",
        "dataset_files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "budget_feasibility": {
            "evidence_sha256": budget_sha,
            "captured_utc": budget["captured_utc"],
            "cli_version": budget["cli_version"],
            "gpu_quota_remaining_hours": budget["gpu_quota_remaining_hours"],
            "platform_max_cpu_gpu_session_seconds": budget["platform_max_cpu_gpu_session_seconds"],
            "requested_kernel_execution_allowance_s": 7200,
            "status": budget["status"],
        },
        "dataset_files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "source_inputs": source_inventory(),
        "preflight_sha256": sha(args.preflight),
        "qualification_flags": {
            "shape_update_allowed": False, "fd_oracle": False, "field_gradient": False,
            "reverse": False, "optimizer": False, "topology": False,
        },
        "not_claimed": ["force response", "FD-08 calibration", "formal result", "qualification"],
    }
    criteria_blob = json.dumps(criteria, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    criteria_sha = hashlib.sha256(criteria_blob).hexdigest()
    manifest = {
        "kind": "fd08_v2_setup_only_dataset_manifest",
        "criteria_sha256": criteria_sha,
        "files": {
            **{name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
            "criteria.json": criteria_sha,
            "criteria.json.sha256": hashlib.sha256((criteria_sha + "\n").encode()).hexdigest(),
        },
    }
    manifest_blob = json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    all_files = {**files, "criteria.json": criteria_blob,
                 "criteria.json.sha256": (criteria_sha + "\n").encode(),
                 "fd08_v2_dataset_manifest.json": manifest_blob}
    for name, blob in all_files.items():
        (args.dataset_dir / name).write_bytes(blob)
    write_json(args.dataset_dir / "dataset-metadata.json", {
        "title": "CFD Opt SDF FD08 V2 Private Inputs",
        "id": "ramhachi888/cfd-opt-sdf-fd08-v2-r6",
        "licenses": [{"name": "other"}],
    })
    args.criteria.parent.mkdir(parents=True, exist_ok=True)
    args.criteria.write_bytes(criteria_blob)
    args.criteria.with_suffix(args.criteria.suffix + ".sha256").write_text(criteria_sha + "\n")
    print(json.dumps({"criteria_sha256": criteria_sha, "dataset_file_count": len(all_files),
                      "source_commit": args.source_commit,
                      "selected_states": [row["name"] for row in chosen]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
