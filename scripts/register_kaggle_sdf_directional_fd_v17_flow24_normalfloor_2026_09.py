#!/usr/bin/env python3
"""Register FD-06 round 1 (#37): the FD-05 contract with one change, normal_floor = 0.25.

Everything measured or judged -- v17 state, flow_24 case, directions, the 30 perturbation
identities, the epsilon ladder, run order, windows, noise/plateau/sign/stationarity gates,
backend and W3/W4 prerequisites -- is taken from the registered FD-05 criteria and asserted
unchanged.  Only the body normal changes (n = g/max(|g|, 0.25)); the floor is the repository's
registered flat-gradient threshold, fixed before any force response under it was run.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import register_kaggle_sdf_directional_fd_v17_flow24_2026_09 as v5

base = v5.base
ROOT = v5.ROOT
CRITERIA_ID = "sdf_directional_fd_v17_flow24_normalfloor_2026_09"
DATASET_ID = "ramhachi888/cfd-opt-sdf-v17-nfloor-directional-fd-oracle"
KERNEL_ID = "ramhachi888/cfd-opt-sdf-v17-nfloor-fd-oracle"
KERNEL_DIR = "infra/kaggle/kernel_sdf_directional_fd_v17_flow24_normalfloor"
NORMAL_FLOOR = 0.25
FD05_CRITERIA = ROOT / "docs/evidence/sdf_directional_fd_v17_flow24_criteria_2026_09_schemafix5.json"
FD05_EVIDENCE = {
    "fd05_kernel1_diagnostic": "docs/evidence/sdf_directional_fd_v17_flow24_kernel1_diagnostic_2026_09.json",
    "fd05_kernel1_host_recomputed_metrics": "docs/evidence/sdf_directional_fd_v17_flow24_kernel1_host_recomputed_metrics_2026_09.json",
    "fd05_solver_free_diagnosis": "docs/evidence/sdf_native_fd05_normal_census_2026_10.json",
    "fd05_force_decomposition": "docs/evidence/sdf_native_fd05_force_decomposition_2026_10.json",
}
OUTPUT = ROOT / "docs/evidence/sdf_directional_fd_v17_flow24_normalfloor_criteria_2026_09.json"
FIXED = ("measurement", "noise_and_plateau", "responses", "backend", "gates", "run_order",
         "direction_inventory", "direction_audit", "perturbation", "perturbation_inventory",
         "prerequisites", "w4_cross_check", "directions", "input_dataset_files")


def build_criteria(source_commit: str, *, require_pushed_head: bool = True) -> dict:
    fd05_sha = base.sha256(FD05_CRITERIA)
    if FD05_CRITERIA.with_suffix(FD05_CRITERIA.suffix + ".sha256").read_text().strip() != fd05_sha:
        raise ValueError("FD-05 criteria sidecar mismatch")
    fd05 = json.loads(FD05_CRITERIA.read_text())
    if fd05["criteria_id"] != v5.CRITERIA_ID or fd05["criteria_round"] != 1:
        raise ValueError("unexpected FD-05 criteria identity")
    evidence = {}
    for name, path_text in FD05_EVIDENCE.items():
        path = ROOT / path_text
        if path.with_suffix(path.suffix + ".sha256").read_text().strip() != base.sha256(path):
            raise ValueError(f"{path_text} sidecar mismatch")
        evidence[name] = base.source_entry(path_text)
    if require_pushed_head:
        branch = subprocess.check_output(["git", "-C", str(ROOT), "branch", "--show-current"], text=True).strip()
        if branch != "codex/kaggle-batch-migration":
            raise ValueError(f"FD-06 criteria must be registered on codex/kaggle-batch-migration, got {branch}")
        if subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
            raise ValueError("FD-06 criteria require a clean registered source checkout")
        head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        upstream = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "@{u}"], text=True).strip()
        if source_commit != head or head != upstream:
            raise ValueError("FD-06 source commit must be the clean pushed codex HEAD")

    metadata = json.loads((ROOT / f"{KERNEL_DIR}/kernel-metadata.json").read_text())
    if metadata.get("id") != KERNEL_ID or metadata.get("dataset_sources") != [DATASET_ID]:
        raise ValueError("FD-06 kernel metadata ID/dataset binding mismatch")

    inputs = {k: v for k, v in v5.source_inputs().items() if k != "superseded_unexecuted_criteria"}
    inputs["kernel_runner"] = base.source_entry(f"{KERNEL_DIR}/runner.py")
    inputs["kernel_metadata"] = base.source_entry(f"{KERNEL_DIR}/kernel-metadata.json")
    inputs["normal_floor_body"] = base.source_entry("julia/CFDSDFWaterLily/src/WaterLilyNormalFloorBody.jl")
    inputs["waterlily_body"] = base.source_entry("julia/CFDSDFWaterLily/src/WaterLilyBody.jl")
    inputs["normal_floor_selftest"] = base.source_entry("julia/CFDSDFWaterLily/test/test_normal_floor.jl")
    inputs["fd06_criteria_registrar"] = base.source_entry(Path(__file__).resolve().relative_to(ROOT).as_posix())
    inputs["fd05_criteria"] = base.source_entry(FD05_CRITERIA.relative_to(ROOT).as_posix())
    inputs["normal_floor_probe_doc"] = base.source_entry("docs/issues/37_fd06_normal_floor_probe.md")
    inputs.update(evidence)
    for name in ("canonical_state_npz", "canonical_phi_fortran_raw"):
        inputs[name] = fd05["inputs"][name]
    for name, entry in fd05["inputs"].items():
        if name.startswith(("direction_", "perturbation_")):
            inputs[name] = entry

    criteria = copy.deepcopy(fd05)
    for key in ("registration_revision", "supersedes", "criteria_sha256"):
        criteria.pop(key, None)
    geometry = criteria["geometry"]
    geometry["normal_floor"] = NORMAL_FLOOR
    geometry["normal_floor_definition"] = "body normal n = g / max(|g|, normal_floor); 0 is the historical n = g/|g|"
    geometry["normal_floor_rationale"] = (
        "0.25 is the repository's registered flat-gradient threshold (FLAT_GRADIENT_THRESHOLD in the v17 genesis "
        "gradient gate), fixed before any force response under a floor was run. FD-05 found 348 flow_24 band samples "
        "with phi~0 and |grad phi|~0 whose normal flips under any perturbation; a solver-free census showed the "
        "floor makes the normal change proportional to epsilon for 0.5-2.5 mm.")
    criteria.update({
        "criteria_id": CRITERIA_ID, "criteria_round": 1,
        "criteria_path": OUTPUT.relative_to(ROOT).as_posix(),
        "kind": "sdf_directional_fd_flow24_normalfloor_criteria",
        "status": "registered_not_run", "immutable": True, "registered_before_computation": True,
        "registered_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "registered_source_commit": source_commit, "source_commit": source_commit,
        "source_tree_commit": source_commit,
        "input_dataset_id": DATASET_ID, "kernel_id": KERNEL_ID, "kernel_title": metadata["title"],
        "dataset_title": "CFD Opt SDF v17 NFloor Directional FD Oracle Inputs",
        "inputs": inputs,
        "source_input_sha256": {n: e["sha256"] for n, e in inputs.items() if e.get("location") == "source_repo"},
        "artifacts": {"dataset_criteria_filename": "sdf_directional_fd_v17_flow24_normalfloor_criteria.json",
                      "dataset_manifest_filename": "sdf_directional_fd_v17_flow24_normalfloor_dataset_manifest.json",
                      "kernel_output_directory": "sdf_directional_fd_v17_flow24_normalfloor",
                      "kernel_log_filename": "fd_run.log"},
        "round_reason": (
            "FD-06: FD-05 (v17, flow_24) failed the 5% plateau gate in all six direction/response combinations with an "
            "epsilon-independent +/- offset. The only change here is the body normal floor (normal_floor=0.25). "
            "All epsilon, window, gate and threshold values, directions and perturbations are the FD-05 contract verbatim."),
        "fd05_reference": {"criteria_path": FD05_CRITERIA.relative_to(ROOT).as_posix(), "criteria_file_sha256": fd05_sha,
                           "criteria_sha256": fd05["criteria_sha256"], "verdict": "terminal FAIL (T10/T11), not a retry",
                           "evidence": {k: v["path"] for k, v in evidence.items()}},
        "primal_note": ("normal_floor changes the primal response; baseline A/B/C are new reference values and are not "
                        "expected to equal the W4 flow_24 values (w4_cross_check stays diagnostic only)."),
        "prior_failed_diagnostic": {"criteria_path": FD05_CRITERIA.relative_to(ROOT).as_posix(),
                                    "criteria_sha256": fd05_sha,
                                    "role": "FD-05 terminal fail-closed result; not a qualification"},
    })
    criteria["claims"]["target"] = (
        "registered WaterLily flow_24 discrete finite-box primal response directional derivative oracle for "
        "canonical v17 SDF with body normal floor 0.25")
    for field in FIXED:
        if criteria[field] != fd05[field]:
            raise ValueError(f"FD-06 changed a FD-05 fixed block: {field}")
    for key in ("canonical_state_sha256", "canonical_phi_fortran_sha256", "point_shape", "flow_case"):
        if criteria["geometry"][key] != fd05["geometry"][key]:
            raise ValueError(f"FD-06 changed FD-05 geometry item: {key}")
    criteria["criteria_sha256"] = base.json_hash(criteria)
    return criteria


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="print a summary without writing or requiring a pushed HEAD")
    args = parser.parse_args()
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if args.preview:
        c = build_criteria(head, require_pushed_head=False)
        print(json.dumps({"criteria_id": c["criteria_id"], "normal_floor": c["geometry"]["normal_floor"],
                          "inputs": len(c["inputs"]), "runs": len(c["run_order"])}, sort_keys=True))
        return 0
    sidecar = OUTPUT.with_suffix(OUTPUT.suffix + ".sha256")
    if OUTPUT.exists() or sidecar.exists():
        raise SystemExit("FD-06 criteria already exist; immutable preregistration will not be overwritten")
    criteria = build_criteria(head)
    OUTPUT.write_text(json.dumps(criteria, indent=2, sort_keys=True, allow_nan=False) + "\n")
    digest = base.sha256(OUTPUT)
    sidecar.write_text(digest + "\n")
    print(json.dumps({"criteria_path": OUTPUT.relative_to(ROOT).as_posix(), "criteria_sha256": digest,
                      "source_commit": head, "perturbations": len(criteria["perturbation_inventory"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
