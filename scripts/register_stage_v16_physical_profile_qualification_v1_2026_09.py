#!/usr/bin/env python3
"""Register numeric gates for the single v2 Stage V physical-profile run.

Registration is solver-free.  The companion runner refuses to start OpenFOAM
unless these immutable artifacts and all pinned source hashes still match.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

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
PROFILE_SPEC = ASSET_ROOT / "project_matched_re_laminar_moving_ground_far_field_v2.yaml"
CANDIDATE = ASSET_ROOT / "v16_candidate_threshold_0p5.iso_surface.stl"
DESIGN_DOMAIN = ASSET_ROOT / "geometry/design_domain.stl"
V2_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_contract_manifest_v2_2026_09.json"
V2_RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_run_manifest_v2_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_qualification_run_manifest_v1_2026_09.json"
MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_qualification_manifest_v1_2026_09.json"
CASE_DIR = ROOT / "work/stage_v_v16_physical_profile_qualification_v1_2026_09/case"
OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _artifact(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"required artifact is missing: {_rel(path)}")
    return {"path": _rel(path), "sha256": _sha256(path)}


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
        raise SystemExit("docker is required to register the controlled OpenFOAM run")
    completed = subprocess.run(
        [docker, "image", "inspect", OPENFOAM_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit("the registered OpenFOAM Docker image is not available")
    return completed.stdout.strip()


def _materialize_and_validate() -> dict[str, Any]:
    spec = load_problem_spec(PROFILE_SPEC)
    config = problem_spec_to_project_config(spec, candidate_stl=CANDIDATE)
    bundle = build_fields(config)
    with tempfile.TemporaryDirectory(prefix="stage_v_profile_qualification_register_") as directory:
        case_dir = Path(directory) / "case"
        generate_openfoam_case(config, bundle, case_dir)
        metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
        velocity = (case_dir / "0/U").read_text(encoding="utf-8")
        pressure = (case_dir / "0/p").read_text(encoding="utf-8")
        required_fragments = (
            "bottom { type translatingWallVelocity; U (1 0 0); value uniform (1 0 0);",
            "inlet { type freestreamVelocity;",
            "inlet { type freestreamPressure; freestreamValue uniform 0; U U;",
        )
        if required_fragments[0] not in velocity or required_fragments[1] not in velocity or required_fragments[2] not in pressure:
            raise SystemExit("v2 renderer did not emit the registered physical-profile boundary contract")
        if metadata["physical_profile"]["sha256"] != "a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca":
            raise SystemExit("v2 physical-profile hash changed before qualification registration")
    preflight = evaluate_stage_v_domain_preflight(
        spec, CANDIDATE, float(spec.grid.voxel_size_m), profile=STAGE_V_CLEARANCE_PROFILE_V1
    )
    if not preflight.qualified:
        raise SystemExit(f"registered v2 candidate fails the pre-mesh clearance gate: {preflight.reasons}")
    return {
        "problem_spec_sha256": problem_spec_sha256(spec),
        "profile_spec_sha256": _sha256(PROFILE_SPEC),
        "candidate_sha256": _sha256(CANDIDATE),
        "design_domain_sha256": _sha256(DESIGN_DOMAIN),
        "physical_profile_sha256": "a84670733ad5009ee57e84b9ee40b19da3254aae45846e5fb7a7f3ae8f72ceca",
        "clearance_preflight": preflight.to_dict(),
    }


def _registered_documents(materialization: dict[str, Any], image_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    source_artifacts = {
        "v2_profile_manifest": _artifact(V2_MANIFEST),
        "v2_profile_run_manifest": _artifact(V2_RUN_MANIFEST),
        "profile_spec": _artifact(PROFILE_SPEC),
        "candidate": _artifact(CANDIDATE),
        "design_domain": _artifact(DESIGN_DOMAIN),
        "renderer": _artifact(ROOT / "src/cfd_sdf/openfoam.py"),
        "solver_gate_module": _artifact(ROOT / "src/cfd_sdf/stage_v_physical_profile.py"),
        "registration_script": _artifact(Path(__file__)),
    }
    gate_profile = {
        "solver_and_mesh": {
            "qualification_profile_id": STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"],
            "qualification_profile": STAGE_V_QUALIFICATION_PROFILE_V1,
            "residual_gate": STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1["solver"],
        },
        "mass_conservation": STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1["mass_conservation"],
        "moving_ground": STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1["moving_ground"],
        "candidate_wall": STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1["candidate_wall"],
        "near_candidate_upstream_velocity": STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1["upstream_velocity"],
        "outer_patch_backflow_and_pressure_disturbance": STAGE_V_PHYSICAL_PROFILE_GATE_PROFILE_V1["outer_boundary"],
        "candidate_clearance": {
            "profile_id": STAGE_V_CLEARANCE_PROFILE_V1["profile_id"],
            "minimum_clearance_m": STAGE_V_CLEARANCE_PROFILE_V1["minimum_clearance_m"],
            "measured_before_any_mesh_command": True,
        },
    }
    question = (
        "Does the v16 candidate become a numerically interpretable Stage V case under the v2 "
        "moving-ground/freestream physical profile on the original V1 box?"
    )
    claims_not_supported = [
        "agreement with the old stationary-ground result",
        "same-profile domain convergence or grid-independent downforce",
        "Stage S reduced-basis FD qualification or a shape update",
        "full-vehicle or high-Re FSAE qualification",
        "an optimization campaign",
    ]
    execution = {
        "solver_started": False,
        "mesh_generation_started": False,
        "optimization_campaign_started": False,
        "new_run_count": 0,
        "maximum_new_runs": 1,
        "case_dir": _rel(CASE_DIR),
    }
    run_document = {
        "kind": "stage_v_v16_physical_profile_qualification_run_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "evidence_class": "contract",
        "question": question,
        "canonical_inputs": {
            "profile_spec": source_artifacts["profile_spec"],
            "candidate": source_artifacts["candidate"],
            "design_domain": source_artifacts["design_domain"],
            "problem_spec_sha256": materialization["problem_spec_sha256"],
            "physical_profile_sha256": materialization["physical_profile_sha256"],
        },
        "docker": {"image": OPENFOAM_IMAGE, "image_id": image_id},
        "gate_profile": gate_profile,
        "clearance_preflight": materialization["clearance_preflight"],
        "source_artifacts": source_artifacts,
        "execution": execution,
        "claims_not_supported": claims_not_supported,
    }
    manifest = {
        "kind": "stage_v_v16_physical_profile_qualification_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "question": question,
        "run_manifest": {"path": _rel(RUN_MANIFEST)},
        "canonical_inputs": run_document["canonical_inputs"],
        "problem_spec_sha256": materialization["problem_spec_sha256"],
        "physical_profile_sha256": materialization["physical_profile_sha256"],
        "docker": run_document["docker"],
        "gate_profile": gate_profile,
        "clearance_preflight": materialization["clearance_preflight"],
        "execution": execution,
        "claims_not_supported": claims_not_supported,
        "source_artifacts": source_artifacts,
    }
    return run_document, manifest


def register() -> dict[str, Any]:
    if any(path.exists() for path in (RUN_MANIFEST, MANIFEST)):
        raise SystemExit("physical-profile qualification manifest already exists; refuse overwrite")
    for path in (V2_MANIFEST, V2_RUN_MANIFEST, PROFILE_SPEC, CANDIDATE, DESIGN_DOMAIN):
        if not path.is_file():
            raise SystemExit(f"required v2 artifact is missing: {_rel(path)}")
    v2 = json.loads(V2_MANIFEST.read_text(encoding="utf-8"))
    if v2.get("status") != "registered_not_run":
        raise SystemExit("the v2 physical-profile contract is not still registered_not_run")
    materialization = _materialize_and_validate()
    image_id = _docker_image_id()
    run_document, manifest = _registered_documents(materialization, image_id)
    run_digest = _write_immutable(RUN_MANIFEST, run_document)
    manifest["run_manifest"]["sha256"] = run_digest
    manifest_digest = _write_immutable(MANIFEST, manifest)
    result = {
        "status": "registered_not_run",
        "run_manifest": _rel(RUN_MANIFEST),
        "run_manifest_sha256": run_digest,
        "manifest": _rel(MANIFEST),
        "manifest_sha256": manifest_digest,
        "physical_profile_sha256": materialization["physical_profile_sha256"],
        "docker_image_id": image_id,
        "solver_started": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def verify() -> dict[str, Any]:
    if not RUN_MANIFEST.is_file() or not MANIFEST.is_file():
        raise SystemExit("physical-profile qualification artifacts are missing")
    run_document = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if run_document.get("status") != "registered_not_run" or manifest.get("status") != "registered_not_run":
        raise SystemExit("qualification manifest is not in registered_not_run state")
    for name, ref in run_document["source_artifacts"].items():
        path = ROOT / ref["path"]
        if _sha256(path) != ref["sha256"]:
            raise SystemExit(f"registered source changed: {name}")
    sidecar = RUN_MANIFEST.with_suffix(RUN_MANIFEST.suffix + ".sha256")
    if _sha256(RUN_MANIFEST) != sidecar.read_text(encoding="utf-8").strip():
        raise SystemExit("qualification run-manifest sidecar mismatch")
    if _sha256(MANIFEST) != MANIFEST.with_suffix(MANIFEST.suffix + ".sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("qualification manifest sidecar mismatch")
    materialization = _materialize_and_validate()
    if materialization["physical_profile_sha256"] != run_document["canonical_inputs"]["physical_profile_sha256"]:
        raise SystemExit("materialized physical-profile hash differs from the registered value")
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

    parser = argparse.ArgumentParser(description="register numeric gates for one Stage V physical-profile run")
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
