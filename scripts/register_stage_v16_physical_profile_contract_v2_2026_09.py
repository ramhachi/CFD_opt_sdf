#!/usr/bin/env python3
"""Register the corrected v16 physical profile without starting OpenFOAM.

The first physical-profile contract used the right conceptual ground model but
did not record the OpenFOAM wall-condition semantic and still carried the old
domain-comparison tolerances.  This v2 contract is self-contained: the
canonical ProblemSpec, design-domain surface, and candidate snapshot are
tracked under ``docs/evidence/assets``.  Registration performs a temporary
case materialization check only; it never invokes a solver or mesh command.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256
from cfd_sdf.sdf import build_fields


ASSET_ROOT = ROOT / "docs/evidence/assets/stage_v_v16_physical_profile_v2"
PROFILE_SPEC = ASSET_ROOT / "project_matched_re_laminar_moving_ground_far_field_v2.yaml"
CANDIDATE = ASSET_ROOT / "v16_candidate_threshold_0p5.iso_surface.stl"
DESIGN_DOMAIN = ASSET_ROOT / "geometry/design_domain.stl"
LINEAGE = ROOT / "docs/evidence/stage_v_v16_physical_profile_candidate_lineage_v2_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_run_manifest_v2_2026_09.json"
MANIFEST = ROOT / "docs/evidence/stage_v_v16_physical_profile_contract_manifest_v2_2026_09.json"

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
PHYSICAL_PROFILE = {
    "boundary_contract": dict(PROFILE_BOUNDARIES),
    "ground_model": "moving_ground",
    "boundary_implementation": {
        "moving_wall": "translatingWallVelocity",
        "far_field_velocity": "freestreamVelocity",
        "far_field_pressure": "freestreamPressure",
    },
    "outer_boundary_semantics": {
        "freestream_velocity_mps": [1.0, 0.0, 0.0],
        "freestream_pressure_pa": 0.0,
    },
    "turbulence_model": "laminar",
    "motion_profiles": dict(PROFILE_MOTION),
}
METRIC = {
    "physical_profile_qualification": {
        "comparison": "new profile only; the old stationary-ground result is not a pass/fail reference",
        "required_before_domain_convergence": True,
        "gates": [
            "solver_convergence",
            "force_stationarity",
            "global_mass_conservation",
            "moving_ground_velocity_and_zero_normal_flux",
            "near_candidate_upstream_velocity",
            "outer_patch_backflow_and_pressure_disturbance",
            "candidate_clearance",
            "mesh_qualification",
        ],
    },
    "same_profile_domain_convergence": {
        "comparison": "compare only cases with identical physical_profile_sha256 and physics, varying domain extent",
        "minimum_treatments": 2,
        "bounds": {
            "downforce_absolute": 0.005,
            "drag_relative": 0.02,
        },
    },
}

SOURCE_LINEAGE = {
    "candidate": {
        "path": "work/pq4_1_v16_state_v2/sweep/threshold_0.5/iso_surface.stl",
        "sha256": "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11",
    },
    "profile_base": {
        "path": "work/stage_sv_laminar/project_matched_re_laminar.yaml",
        "sha256": "dd704b42021334c4e25261c8a2bbc606c4268a5dcbc4e6df0baf8b48d87b7417",
    },
    "profile_v1": {
        "path": "work/stage_v_v16_physical_profile_2026_09/specs/project_matched_re_laminar_moving_ground_far_field_v1.yaml",
        "sha256": "3051b089de1642b93525a4d3f7ce89c5755f61fc6931101aa0eec177f2b2f278",
    },
    "stage_s_handoff_manifest": {
        "path": "work/pq4_1_v16_state_v2/sweep/threshold_0.5/handoff_manifest.json",
        "sha256": "a79135e33b9869b356050984f04e209a3210e4dc4b11d160e45fc82d839952c7",
    },
}


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
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"immutable sidecar mismatch: {_rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8")
    return digest


def _materialize_and_validate() -> dict[str, Any]:
    spec = load_problem_spec(PROFILE_SPEC)
    canonical_spec_digest = problem_spec_sha256(spec)
    config = problem_spec_to_project_config(spec, candidate_stl=CANDIDATE)
    bundle = build_fields(config)
    with tempfile.TemporaryDirectory(prefix="stage_v_v16_profile_v2_") as directory:
        case_dir = Path(directory) / "case"
        generate_openfoam_case(config, bundle, case_dir)
        velocity = (case_dir / "0" / "U").read_text(encoding="utf-8")
        pressure = (case_dir / "0" / "p").read_text(encoding="utf-8")
        if "bottom { type translatingWallVelocity; U (1 0 0); value uniform (1 0 0);" not in velocity:
            raise SystemExit("moving-ground renderer did not emit translatingWallVelocity")
        if "inlet { type freestreamVelocity;" not in velocity:
            raise SystemExit("far-field velocity renderer did not emit freestreamVelocity")
        if "inlet { type freestreamPressure; freestreamValue uniform 0; U U;" not in pressure:
            raise SystemExit("far-field pressure renderer did not emit freestreamPressure")
        metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
    actual_profile = dict(metadata["physical_profile"])
    actual_profile.pop("sha256", None)
    if actual_profile != PHYSICAL_PROFILE:
        raise SystemExit(
            "renderer physical_profile differs from the registered contract: "
            f"{json.dumps(actual_profile, sort_keys=True)}"
        )
    return {
        "profile_spec_sha256": _sha256(PROFILE_SPEC),
        "problem_spec_sha256": canonical_spec_digest,
        "candidate_sha256": _sha256(CANDIDATE),
        "design_domain_sha256": _sha256(DESIGN_DOMAIN),
        "physical_profile_sha256": metadata["physical_profile"]["sha256"],
    }


def register() -> dict[str, Any]:
    if RUN_MANIFEST.exists() or MANIFEST.exists() or LINEAGE.exists():
        raise SystemExit("the corrected v2 physical-profile contract already exists; refuse overwrite")
    for path in (PROFILE_SPEC, CANDIDATE, DESIGN_DOMAIN):
        if not path.is_file():
            raise SystemExit(f"canonical v2 asset is missing: {_rel(path)}")

    materialization = _materialize_and_validate()
    lineage_document = {
        "kind": "stage_v_v16_physical_profile_candidate_lineage",
        "schema_version": 1,
        "immutable": True,
        "source_lineage": SOURCE_LINEAGE,
        "canonical_snapshot": {
            "profile_spec": _artifact(PROFILE_SPEC),
            "candidate": _artifact(CANDIDATE),
            "design_domain": _artifact(DESIGN_DOMAIN),
        },
        "reconstruction": {
            "profile_spec": _rel(PROFILE_SPEC),
            "candidate": _rel(CANDIDATE),
            "generator": _rel(Path(__file__)),
            "renderer": _rel(ROOT / "src/cfd_sdf/openfoam.py"),
            "solver_invoked": False,
        },
    }
    lineage_digest = _write_immutable(LINEAGE, lineage_document)
    artifacts = {
        "profile_spec": _artifact(PROFILE_SPEC),
        "candidate": _artifact(CANDIDATE),
        "design_domain": _artifact(DESIGN_DOMAIN),
        "candidate_lineage": {"path": _rel(LINEAGE), "sha256": lineage_digest},
        "registration_script": _artifact(Path(__file__)),
        "renderer": _artifact(ROOT / "src/cfd_sdf/openfoam.py"),
    }
    run_document = {
        "kind": "stage_v_v16_physical_profile_contract_manifest_v2",
        "schema_version": 2,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "evidence_class": "contract",
        "question": (
            "Does the same v16 candidate become physically interpretable when the original V1 box "
            "uses translatingWallVelocity moving-ground and freestream outer-boundary semantics?"
        ),
        "supersedes": {
            "manifest": "docs/evidence/stage_v_v16_physical_profile_contract_manifest_2026_09.json",
            "reason": "v1 used movingWallVelocity and conflated physical-profile qualification with domain convergence",
        },
        "canonical_inputs": {
            "profile_spec": artifacts["profile_spec"],
            "candidate": artifacts["candidate"],
            "design_domain": artifacts["design_domain"],
        },
        "candidate_lineage": artifacts["candidate_lineage"],
        "physical_profile": PHYSICAL_PROFILE,
        "problem_spec_sha256": materialization["problem_spec_sha256"],
        "physical_profile_sha256": materialization["physical_profile_sha256"],
        "metric": METRIC,
        "execution": {
            "solver_started": False,
            "mesh_generation_started": False,
            "optimization_campaign_started": False,
            "new_run_count": 0,
        },
        "claims_not_supported": [
            "agreement with the old stationary-ground result",
            "solver qualification or grid-independent downforce",
            "same-profile domain convergence before a physical-profile pass",
            "Stage S reduced-basis FD qualification",
            "full-vehicle or high-Re FSAE qualification",
        ],
        "artifacts": artifacts,
    }
    run_digest = _write_immutable(RUN_MANIFEST, run_document)
    manifest = {
        "kind": "stage_v_v16_physical_profile_contract_v2",
        "schema_version": 2,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": run_digest},
        "question": run_document["question"],
        "supersedes": run_document["supersedes"],
        "canonical_inputs": run_document["canonical_inputs"],
        "candidate_lineage": artifacts["candidate_lineage"],
        "physical_profile": PHYSICAL_PROFILE,
        "problem_spec_sha256": materialization["problem_spec_sha256"],
        "physical_profile_sha256": materialization["physical_profile_sha256"],
        "metric": METRIC,
        "claims_not_supported": run_document["claims_not_supported"],
    }
    manifest_digest = _write_immutable(MANIFEST, manifest)
    result = {
        "run_manifest": _rel(RUN_MANIFEST),
        "run_manifest_sha256": run_digest,
        "manifest": _rel(MANIFEST),
        "manifest_sha256": manifest_digest,
        "candidate_lineage": _rel(LINEAGE),
        "physical_profile_sha256": materialization["physical_profile_sha256"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def verify() -> dict[str, Any]:
    if not RUN_MANIFEST.is_file() or not MANIFEST.is_file() or not LINEAGE.is_file():
        raise SystemExit("corrected v2 physical-profile artifacts are missing")
    run_document = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if run_document.get("status") != "registered_not_run" or manifest.get("status") != "registered_not_run":
        raise SystemExit("corrected v2 physical-profile contract is not in registered_not_run state")
    for record in run_document["artifacts"].values():
        path = ROOT / record["path"]
        if _sha256(path) != record["sha256"]:
            raise SystemExit(f"registered artifact changed: {record['path']}")
    materialization = _materialize_and_validate()
    if materialization["physical_profile_sha256"] != run_document["physical_profile_sha256"]:
        raise SystemExit("materialized physical profile hash differs from the registered hash")
    result = {
        "status": "pass",
        "solver_started": run_document["execution"]["solver_started"],
        "physical_profile_sha256": materialization["physical_profile_sha256"],
        "manifest_sha256": _sha256(MANIFEST),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="register the corrected v2 physical profile without running OpenFOAM")
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
