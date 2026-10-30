#!/usr/bin/env python3
"""Register the next solver-free v16 physical boundary profile.

The previous v16 domain ladder changed the upstream development length while
keeping a stationary ground.  This contract freezes the original V1 box and
declares the physical profile explicitly: a moving ground and far-field outer
patches.  Registration only materialises and hashes the derived ProblemSpec;
it never starts OpenFOAM.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
CANDIDATE = ROOT / "work/pq4_1_v16_state_v2/sweep/threshold_0.5/iso_surface.stl"
OUT_ROOT = ROOT / "work/stage_v_v16_physical_profile_2026_09"
SPEC_ROOT = OUT_ROOT / "specs"
PROFILE_SPEC = SPEC_ROOT / "project_matched_re_laminar_moving_ground_far_field_v1.yaml"
PROFILE_DOMAIN_STL = SPEC_ROOT / "geometry/design_domain.stl"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_run_manifest_2026_09.json"
MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_contract_manifest_2026_09.json"

PROFILE_BOUNDARIES = {
    "inlet": "far_field",
    "outlet": "far_field",
    "sideMin": "far_field",
    "sideMax": "far_field",
    "top": "far_field",
    "bottom": "moving_wall",
}
PROFILE_MOTION = {
    "moving_ground": {
        "kind": "translation",
        "boundary_ids": ["bottom"],
        "velocity_mps": [1.0, 0.0, 0.0],
    }
}
PROFILE_ID = "stage_sv_laminar_matched_re_moving_ground_far_field_v1"


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
        path.write_text(payload, encoding="utf-8")
    digest = _sha256(path)
    sidecar = path.with_suffix(".json.sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"immutable sidecar mismatch: {_rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8")
    return digest


def _profile_spec_document() -> dict[str, Any]:
    if not BASE_SPEC.is_file():
        raise SystemExit(f"base ProblemSpec is missing: {_rel(BASE_SPEC)}")
    document = copy.deepcopy(yaml.safe_load(BASE_SPEC.read_text(encoding="utf-8")))
    document["problem_id"] = PROFILE_ID
    flow_cases = document.get("flow_cases")
    if not isinstance(flow_cases, list) or len(flow_cases) != 1:
        raise SystemExit("the v16 physical profile requires exactly one base flow case")
    flow_case = flow_cases[0]
    flow_case["boundary_conditions"] = copy.deepcopy(PROFILE_BOUNDARIES)
    flow_case["motion_profiles"] = copy.deepcopy(PROFILE_MOTION)
    return document


def _ensure_profile_spec() -> dict[str, Any]:
    document = _profile_spec_document()
    SPEC_ROOT.mkdir(parents=True, exist_ok=True)
    if PROFILE_SPEC.exists():
        if yaml.safe_load(PROFILE_SPEC.read_text(encoding="utf-8")) != document:
            raise SystemExit("the registered physical-profile ProblemSpec differs")
    else:
        PROFILE_SPEC.write_text(
            yaml.safe_dump(document, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    PROFILE_DOMAIN_STL.parent.mkdir(parents=True, exist_ok=True)
    source_domain = BASE_SPEC.parent / "geometry" / "design_domain.stl"
    if not source_domain.is_file():
        raise SystemExit(f"base design-domain STL is missing: {_rel(source_domain)}")
    if PROFILE_DOMAIN_STL.exists():
        if _sha256(PROFILE_DOMAIN_STL) != _sha256(source_domain):
            raise SystemExit("the staged physical-profile design-domain STL differs")
    else:
        shutil.copyfile(source_domain, PROFILE_DOMAIN_STL)
    return {
        "path": _rel(PROFILE_SPEC),
        "sha256": _sha256(PROFILE_SPEC),
        "staged_design_domain": _artifact(PROFILE_DOMAIN_STL),
    }


def register() -> dict[str, Any]:
    if RUN_MANIFEST.exists() or MANIFEST.exists():
        raise SystemExit("the v16 physical-profile contract already exists; refuse overwrite")
    if not CANDIDATE.is_file():
        raise SystemExit(f"registered v16 candidate is missing: {_rel(CANDIDATE)}")

    profile_spec = _ensure_profile_spec()
    document = {
        "kind": "stage_v_v16_physical_profile_contract_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "evidence_class": "contract",
        "question": (
            "Does the same v16 candidate become physically interpretable when the original V1 box "
            "uses an explicit moving-ground and far-field outer-boundary profile?"
        ),
        "rationale": {
            "stationary_ground_confound": (
                "The closed domain ladder moved the inlet together with the outer box while keeping "
                "a no-slip ground, changing upstream boundary-layer development."
            ),
            "profile_scope": "reduced laminar external-aero benchmark; not FSAE/high-Re qualification",
        },
        "candidate": {"stl": _artifact(CANDIDATE), "same_candidate_as_stage_s": True},
        "base_spec": _artifact(BASE_SPEC),
        "profile_spec": profile_spec,
        "physical_profile": {
            "ground_model": "moving_ground",
            "boundary_contract": dict(PROFILE_BOUNDARIES),
            "motion_profiles": copy.deepcopy(PROFILE_MOTION),
            "outer_boundary_semantics": {
                "U": "freestreamVelocity",
                "p": "freestreamPressure",
                "freestream_velocity_mps": [1.0, 0.0, 0.0],
                "freestream_pressure": 0.0,
            },
        },
        "metric": {
            "comparison": "one profile at the original V1 box; no domain ladder claim",
            "downforce_absolute": 0.005,
            "drag_relative": 0.02,
        },
        "execution": {
            "solver_started": False,
            "mesh_generation_started": False,
            "optimization_campaign_started": False,
            "new_run_count": 0,
        },
        "claims_not_supported": [
            "solver qualification or grid-independent downforce",
            "Stage S reduced-basis FD qualification",
            "full-vehicle or high-Re FSAE qualification",
        ],
        "artifacts": {
            "base_spec": _artifact(BASE_SPEC),
            "candidate": _artifact(CANDIDATE),
            "profile_spec": profile_spec,
            "registration_script": _artifact(Path(__file__)),
        },
    }
    run_digest = _write_immutable(RUN_MANIFEST, document)
    manifest = {
        "kind": "stage_v_v16_physical_profile_contract",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": run_digest},
        "question": document["question"],
        "candidate": document["candidate"],
        "profile_spec": profile_spec,
        "physical_profile": document["physical_profile"],
        "metric": document["metric"],
        "claims_not_supported": document["claims_not_supported"],
    }
    manifest_digest = _write_immutable(MANIFEST, manifest)
    result = {
        "run_manifest": _rel(RUN_MANIFEST),
        "run_manifest_sha256": run_digest,
        "manifest": _rel(MANIFEST),
        "manifest_sha256": manifest_digest,
        "profile_spec": profile_spec,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def verify() -> dict[str, Any]:
    if not RUN_MANIFEST.is_file() or not MANIFEST.is_file():
        raise SystemExit("physical-profile contract artifacts are missing")
    run_document = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if run_document.get("status") != "registered_not_run" or manifest.get("status") != "registered_not_run":
        raise SystemExit("physical-profile contract is not in registered_not_run state")
    for record in run_document["artifacts"].values():
        path = ROOT / record["path"]
        if _sha256(path) != record["sha256"]:
            raise SystemExit(f"registered artifact changed: {record['path']}")
    result = {
        "status": "pass",
        "solver_started": run_document["execution"]["solver_started"],
        "profile_spec_sha256": _sha256(PROFILE_SPEC),
        "manifest_sha256": _sha256(MANIFEST),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="register the v16 physical profile without running OpenFOAM")
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
