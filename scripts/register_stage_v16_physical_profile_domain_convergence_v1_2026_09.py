#!/usr/bin/env python3
"""Register one same-profile domain for the convergence pair."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1
from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256
from cfd_sdf.sdf import build_fields
from cfd_sdf.stage_v_domain_preflight import STAGE_V_CLEARANCE_PROFILE_V1, evaluate_stage_v_domain_preflight
from cfd_sdf.stage_v_physical_profile import STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1


ASSET_ROOT = ROOT / "docs/evidence/assets/stage_v_v16_physical_profile_v2"
BASE_SPEC = ASSET_ROOT / "project_matched_re_laminar_moving_ground_far_field_v2_expanded_domain_v2.yaml"
EXPANDED_SPEC = ASSET_ROOT / "project_matched_re_laminar_moving_ground_far_field_v2_expanded_domain_v3.yaml"
CANDIDATE = ASSET_ROOT / "v16_candidate_threshold_0p5.iso_surface.stl"
DESIGN_DOMAIN = ASSET_ROOT / "geometry/design_domain.stl"
PARENT_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_manifest_v1_2026_09.json"
PARENT_RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_run_manifest_v1_2026_09.json"
PARENT_OUTCOME = ROOT / "docs/evidence/stage_v_v16_physical_profile_expanded_domain_v2_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_domain_convergence_v1_run_manifest_2026_09.json"
MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_domain_convergence_v1_manifest_2026_09.json"
CASE_DIR = ROOT / "work/stage_v_v16_physical_profile_domain_convergence_v1_2026_09/case"
OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"
PHYSICAL_PROFILE_SHA = "a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _artifact(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"required artifact is missing: {_rel(path)}")
    return {"path": _rel(path), "sha256": _sha256(path)}


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"required JSON is missing: {_rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_immutable(path: Path, document: dict[str, Any]) -> str:
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise SystemExit(f"refusing to overwrite immutable artifact: {_rel(path)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(payload, encoding="utf-8", newline="\n")
    digest = _sha256(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"immutable sidecar mismatch: {_rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8", newline="\n")
    return digest


def _docker_image_id() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise SystemExit("docker is required for the controlled domain-expansion run")
    completed = subprocess.run(
        [docker, "image", "inspect", OPENFOAM_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit("the registered OpenFOAM Docker image is unavailable")
    return completed.stdout.strip()


def _physics_equal_except_domain() -> dict[str, Any]:
    base = yaml.safe_load(BASE_SPEC.read_text(encoding="utf-8"))
    expanded = yaml.safe_load(EXPANDED_SPEC.read_text(encoding="utf-8"))
    base_cmp = copy.deepcopy(base)
    expanded_cmp = copy.deepcopy(expanded)
    base_cmp.pop("problem_id", None)
    expanded_cmp.pop("problem_id", None)
    base_cmp["grid"].pop("domain_bounds_m", None)
    expanded_cmp["grid"].pop("domain_bounds_m", None)
    if base_cmp != expanded_cmp:
        raise SystemExit("expanded ProblemSpec changes physics or geometry outside grid bounds")
    return {
        "base_problem_id": base["problem_id"],
        "expanded_problem_id": expanded["problem_id"],
        "base_domain_bounds_m": base["grid"]["domain_bounds_m"],
        "expanded_domain_bounds_m": expanded["grid"]["domain_bounds_m"],
        "only_domain_bounds_changed": True,
    }


def _materialize_and_validate() -> dict[str, Any]:
    spec = load_problem_spec(EXPANDED_SPEC)
    config = problem_spec_to_project_config(spec, candidate_stl=CANDIDATE)
    bundle = build_fields(config)
    with tempfile.TemporaryDirectory(prefix="stage_v_profile_expanded_register_") as directory:
        case_dir = Path(directory) / "case"
        generate_openfoam_case(config, bundle, case_dir)
        metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
        if metadata.get("problem_id") != spec.problem_id:
            raise SystemExit("expanded case metadata has the wrong ProblemSpec identity")
        if metadata.get("physical_profile", {}).get("sha256") != PHYSICAL_PROFILE_SHA:
            raise SystemExit("expanded domain changed the registered physical-profile hash")
        if _sha256(case_dir / "constant/triSurface/design_candidate.stl") != _sha256(CANDIDATE):
            raise SystemExit("expanded case candidate hash changed")
    preflight = evaluate_stage_v_domain_preflight(
        spec, CANDIDATE.resolve(), float(spec.grid.voxel_size_m), profile=STAGE_V_CLEARANCE_PROFILE_V1
    )
    if not preflight.qualified:
        raise SystemExit(f"expanded domain fails pre-mesh clearance: {preflight.reasons}")
    return {
        "problem_spec_sha256": problem_spec_sha256(spec),
        "expanded_spec_sha256": _sha256(EXPANDED_SPEC),
        "candidate_sha256": _sha256(CANDIDATE),
        "design_domain_sha256": _sha256(DESIGN_DOMAIN),
        "physical_profile_sha256": PHYSICAL_PROFILE_SHA,
        "clearance_preflight": preflight.to_dict(),
    }


def _documents(
    materialization: dict[str, Any],
    image_id: str,
    physics: dict[str, Any],
    parent_outcome: dict[str, Any],
    parent_run_manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_artifacts = {
        "parent_manifest": _artifact(PARENT_MANIFEST),
        "parent_run_manifest": _artifact(PARENT_RUN_MANIFEST),
        "parent_outcome": _artifact(PARENT_OUTCOME),
        "base_spec": _artifact(BASE_SPEC),
        "expanded_spec": _artifact(EXPANDED_SPEC),
        "candidate": _artifact(CANDIDATE),
        "design_domain": _artifact(DESIGN_DOMAIN),
        "renderer": _artifact(ROOT / "src/cfd_sdf/openfoam.py"),
        "solver_gate_module": _artifact(ROOT / "src/cfd_sdf/stage_v_physical_profile.py"),
        "registration_script": _artifact(Path(__file__)),
    }
    parent_gate_profile = parent_run_manifest["gate_profile"]
    question = "Does the same v2 physical profile converge when downstream clearance increases?"
    execution = {
        "solver_started": False,
        "mesh_generation_started": False,
        "optimization_campaign_started": False,
        "new_run_count": 0,
        "maximum_new_runs": 1,
        "case_dir": _rel(CASE_DIR),
    }
    run_document = {
        "kind": "stage_v_v16_physical_profile_domain_convergence_run_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "evidence_class": "contract",
        "question": question,
        "parent_v2": {
            "manifest": _artifact(PARENT_MANIFEST),
            "run_manifest": _artifact(PARENT_RUN_MANIFEST),
            "outcome": _artifact(PARENT_OUTCOME),
            "outcome_status": parent_outcome["status"],
            "outcome_qualified": parent_outcome["qualified"],
        },
        "domain_factor": physics,
        "canonical_inputs": {
            "expanded_spec": source_artifacts["expanded_spec"],
            "candidate": source_artifacts["candidate"],
            "design_domain": source_artifacts["design_domain"],
            "problem_spec_sha256": materialization["problem_spec_sha256"],
            "physical_profile_sha256": materialization["physical_profile_sha256"],
        },
        "docker": {"image": OPENFOAM_IMAGE, "image_id": image_id},
        "gate_profile": parent_gate_profile,
        "domain_convergence_profile": {
            "downforce_absolute_delta_threshold": 0.005,
            "cd_relative_delta_threshold": 0.02,
            "comparison_denominator": "parent_v2_cd_mean",
            "requires_both_physical_profile_outcomes_qualified": True,
        },
        "clearance_preflight": materialization["clearance_preflight"],
        "source_artifacts": source_artifacts,
        "execution": execution,
        "claims_not_supported": [
            "agreement with the old stationary-ground result",
            "same-profile domain convergence before this profile passes",
            "grid-independent or absolute downforce",
            "Stage S reduced-basis FD qualification or a shape update",
            "an optimization campaign",
        ],
    }
    manifest = {
        "kind": "stage_v_v16_physical_profile_domain_convergence_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "question": question,
        "run_manifest": {"path": _rel(RUN_MANIFEST)},
        "parent_v2": run_document["parent_v2"],
        "domain_factor": physics,
        "canonical_inputs": run_document["canonical_inputs"],
        "problem_spec_sha256": materialization["problem_spec_sha256"],
        "physical_profile_sha256": materialization["physical_profile_sha256"],
        "docker": run_document["docker"],
        "gate_profile": parent_gate_profile,
        "domain_convergence_profile": run_document["domain_convergence_profile"],
        "clearance_preflight": materialization["clearance_preflight"],
        "execution": execution,
        "source_artifacts": source_artifacts,
        "claims_not_supported": run_document["claims_not_supported"],
    }
    return run_document, manifest


def register() -> dict[str, Any]:
    if any(path.exists() for path in (RUN_MANIFEST, MANIFEST)):
        raise SystemExit("domain-convergence manifest already exists; refuse overwrite")
    for path in (BASE_SPEC, EXPANDED_SPEC, CANDIDATE, DESIGN_DOMAIN, PARENT_MANIFEST, PARENT_RUN_MANIFEST, PARENT_OUTCOME):
        if not path.is_file():
            raise SystemExit(f"required parent or expanded artifact is missing: {_rel(path)}")
    parent_manifest = _load(PARENT_RUN_MANIFEST)
    parent = _load(PARENT_OUTCOME)
    if parent_manifest.get("status") != "registered_not_run":
        raise SystemExit("parent v2 run manifest is not immutable registered_not_run")
    if parent.get("status") != "pass" or parent.get("qualified") is not True:
        raise SystemExit("domain convergence requires the qualified parent v2 physical-profile outcome")
    required_passes = (
        "identity",
        "candidate_clearance",
        "mesh_qualification",
        "solver_convergence",
        "solver_final_residuals",
        "force_stationarity",
        "global_mass_conservation",
        "moving_ground_velocity_and_zero_normal_flux",
        "candidate_zero_normal_flux",
        "near_candidate_upstream_velocity",
        "outer_patch_backflow_and_pressure_disturbance",
    )
    for gate_name in required_passes:
        gate = parent["gates"].get(gate_name, {})
        if not gate.get("qualified", gate.get("status") == "pass"):
            raise SystemExit(f"parent gate {gate_name} did not pass")
    if parent["gates"]["outer_patch_backflow_and_pressure_disturbance"].get("status") != "pass":
        raise SystemExit("parent physical-profile outer-field gate is not pass")
    if parent["run_manifest"]["sha256"] != _sha256(PARENT_RUN_MANIFEST):
        raise SystemExit("parent outcome does not point to the current parent run manifest")
    if parent["docker"]["image_id"] != _docker_image_id():
        raise SystemExit("Docker image identity changed since parent run")
    physics = _physics_equal_except_domain()
    materialization = _materialize_and_validate()
    run_document, manifest = _documents(
        materialization,
        parent["docker"]["image_id"],
        physics,
        parent,
        parent_manifest,
    )
    run_digest = _write_immutable(RUN_MANIFEST, run_document)
    manifest["run_manifest"]["sha256"] = run_digest
    manifest_digest = _write_immutable(MANIFEST, manifest)
    result = {
        "status": "registered_not_run",
        "run_manifest": _rel(RUN_MANIFEST),
        "run_manifest_sha256": run_digest,
        "manifest": _rel(MANIFEST),
        "manifest_sha256": manifest_digest,
        "expanded_problem_spec_sha256": materialization["problem_spec_sha256"],
        "physical_profile_sha256": PHYSICAL_PROFILE_SHA,
        "solver_started": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def verify() -> dict[str, Any]:
    run_document = _load(RUN_MANIFEST)
    manifest = _load(MANIFEST)
    if run_document.get("status") != "registered_not_run" or manifest.get("status") != "registered_not_run":
        raise SystemExit("domain-convergence contract is not registered_not_run")
    for name, ref in run_document["source_artifacts"].items():
        if _sha256(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"registered domain-convergence source changed: {name}")
    for path in (RUN_MANIFEST, MANIFEST):
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if _sha256(path) != sidecar.read_text(encoding="utf-8").strip():
            raise SystemExit(f"domain-convergence sidecar mismatch: {_rel(sidecar)}")
    materialization = _materialize_and_validate()
    if materialization["physical_profile_sha256"] != run_document["canonical_inputs"]["physical_profile_sha256"]:
        raise SystemExit("domain-convergence materialization changed the physical-profile hash")
    result = {
        "status": "pass",
        "solver_started": run_document["execution"]["solver_started"],
        "manifest_sha256": _sha256(MANIFEST),
        "physical_profile_sha256": materialization["physical_profile_sha256"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="register one same-profile domain-convergence Stage V contract")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.verify:
        verify()
    else:
        parser.error("specify --register or --verify")


if __name__ == "__main__":
    main()
