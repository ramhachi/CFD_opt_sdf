#!/usr/bin/env python3
"""Final planned same-candidate v16 domain continuation at +3.2 m."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_v16_domain_continuation_2026_09 as base  # noqa: E402
from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1, evaluate_check_mesh, write_stage_v_qualification  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.stage_v_domain_preflight import evaluate_stage_v_domain_preflight, write_stage_v_domain_preflight_report  # noqa: E402
from stage_t_filtered_ramp import MESH_ONLY_ALLRUN, SOLVE_ONLY_ALLRUN, _write_stagev_level_preflight  # noqa: E402


EXTENSION_M = 3.2
OUT_ROOT = ROOT / "work/stage_v_v16_domain_continuation_3p2_2026_09"
SPEC_ROOT = OUT_ROOT / "specs"
EXT_SPEC = SPEC_ROOT / "project_matched_re_laminar_domain_extended_3p2_v1.yaml"
EXT_DOMAIN_STL = SPEC_ROOT / "geometry/design_domain.stl"
CASE_DIR = OUT_ROOT / "far_field_domain_extension_3p2/V1"

PARENT_MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_continuation_3p2_manifest_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_continuation_3p2_run_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_v16_domain_continuation_3p2_2026_09.json"

FACTOR_MANIFEST = base.v16.MANIFEST
FACTOR_EVIDENCE = base.v16.EVIDENCE
FACTOR_LINEAGE = base.LINEAGE_AUDIT
PREVIOUS_MANIFEST = base.RUN_MANIFEST
PREVIOUS_EVIDENCE = base.EVIDENCE
CANDIDATE = base.CANDIDATE
BASE_SPEC = base.BASE_SPEC
BASELINE_CASE = base.BASELINE_CASE
PREVIOUS_CASE = base.CASE_DIR
V16_CANDIDATE_SHA = base.V16_CANDIDATE_SHA
V1_VOXEL_M = base.V1_VOXEL_M
OPENFOAM_IMAGE = base.OPENFOAM_IMAGE


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"required file is missing: {_rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(path: Path, expected: str | None = None) -> dict[str, str]:
    observed = _sha256(path)
    if expected is not None and observed != expected:
        raise SystemExit(f"hash mismatch for {_rel(path)}: expected {expected}, observed {observed}")
    return {"path": _rel(path), "sha256": observed}


def _write_immutable(path: Path, document: dict[str, Any]) -> str:
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise SystemExit(f"refusing to overwrite immutable artifact: {_rel(path)}")
    if not path.exists():
        path.write_text(payload, encoding="utf-8")
    digest = _sha256(path)
    sidecar = path.with_suffix(".json.sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"sidecar mismatch: {_rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8")
    return digest


def _responses(qualification: dict[str, Any]) -> dict[str, Any]:
    responses = qualification["force_stationarity"]["responses"]
    return {
        "qualified": bool(qualification.get("qualified")),
        "reasons": list(qualification.get("reasons", [])),
        "cells": int(qualification["check_mesh"]["total_cells"]),
        "iterations": qualification["solver"].get("iteration_count"),
        "Cd": float(responses["Cd"]["mean"]),
        "downforce": float(responses["downforce"]["mean"]),
        "raw_check_mesh_mesh_ok": bool(qualification["check_mesh"].get("mesh_ok")),
    }


def _configure_base() -> None:
    base.CONTINUATION_M = EXTENSION_M
    base.OUT_ROOT = OUT_ROOT
    base.SPEC_ROOT = SPEC_ROOT
    base.EXT_SPEC = EXT_SPEC
    base.EXT_DOMAIN_STL = EXT_DOMAIN_STL
    base.CASE_DIR = CASE_DIR


def register() -> dict[str, Any]:
    if any(path.exists() for path in (PARENT_MANIFEST, RUN_MANIFEST, EVIDENCE)):
        raise SystemExit("v16 +3.2 continuation artifacts already exist; refuse overwrite")
    factor_evidence = _load(FACTOR_EVIDENCE)
    previous_evidence = _load(PREVIOUS_EVIDENCE)
    lineage = _load(FACTOR_LINEAGE)
    if factor_evidence.get("decision") != "v16 factor response remains outside the registered band; keep S2 blocked and register a revised contract":
        raise SystemExit("v16 factor No-Go is missing")
    if previous_evidence.get("decision") != "v16 domain response remains moving beyond the registered band; register the next continuation or a physically justified far-field contract and keep S2 blocked":
        raise SystemExit("the +1.6 m continuation did not authorize +3.2 m")
    if lineage.get("status") != "pass":
        raise SystemExit("v16 factor lineage audit did not pass")
    if _sha256(CANDIDATE) != V16_CANDIDATE_SHA:
        raise SystemExit("the registered v16 candidate STL changed")
    factor_manifest = _load(FACTOR_MANIFEST)
    baseline_qualification = _load(BASELINE_CASE / "stage_v_qualification.json")
    previous_qualification = _load(PREVIOUS_CASE / "stage_v_qualification.json")
    if not baseline_qualification.get("qualified") or not previous_qualification.get("qualified"):
        raise SystemExit("baseline and +1.6 m qualification must be profile-qualified")
    _configure_base()
    inputs = base._ensure_inputs()
    baseline = {"case_dir": _rel(BASELINE_CASE), **_responses(baseline_qualification)}
    previous = {"case_dir": _rel(PREVIOUS_CASE), **_responses(previous_qualification)}
    treatment = {
        "name": "far_field_domain_extension_3p2",
        "factor": "far-field domain size",
        "change": "extend inlet, outlet, sideMin, sideMax, and top by 3.2 m from the original v16 V1 box; bottom remains at z=-0.6 m",
        "far_field_faces": list(base.v16.FAR_FIELD_FACES),
        "ground_face": base.v16.GROUND_FACE,
        "boundary_contract": factor_manifest["common_conditions"]["boundary_contract"],
        "extended_spec": inputs,
        "case_dir": _rel(CASE_DIR),
    }
    artifacts = {
        _rel(FACTOR_MANIFEST): _artifact(FACTOR_MANIFEST),
        _rel(FACTOR_EVIDENCE): _artifact(FACTOR_EVIDENCE),
        _rel(FACTOR_LINEAGE): _artifact(FACTOR_LINEAGE),
        _rel(PREVIOUS_MANIFEST): _artifact(PREVIOUS_MANIFEST),
        _rel(PREVIOUS_EVIDENCE): _artifact(PREVIOUS_EVIDENCE),
        _rel(CANDIDATE): _artifact(CANDIDATE, V16_CANDIDATE_SHA),
        _rel(BASE_SPEC): _artifact(BASE_SPEC),
        _rel(base.v16.DOMAIN_STL): _artifact(base.v16.DOMAIN_STL),
        _rel(BASELINE_CASE / "stage_v_qualification.json"): _artifact(BASELINE_CASE / "stage_v_qualification.json"),
        _rel(PREVIOUS_CASE / "stage_v_qualification.json"): _artifact(PREVIOUS_CASE / "stage_v_qualification.json"),
        _rel(EXT_SPEC): _artifact(EXT_SPEC),
        _rel(EXT_DOMAIN_STL): _artifact(EXT_DOMAIN_STL),
        _rel(Path(__file__)): _artifact(Path(__file__)),
    }
    run_document = {
        "kind": "stage_v_v16_domain_continuation_3p2_run_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "evidence_class": "contract",
        "question": "Does the same-candidate v16 response settle when the original V1 domain is extended by 3.2 m under unchanged symmetry/freestream/wall boundary semantics?",
        "parents": {"factor_manifest": _artifact(FACTOR_MANIFEST), "factor_evidence": _artifact(FACTOR_EVIDENCE), "factor_lineage": _artifact(FACTOR_LINEAGE), "previous_run_manifest": _artifact(PREVIOUS_MANIFEST), "previous_evidence": _artifact(PREVIOUS_EVIDENCE)},
        "candidate": {"stl": _artifact(CANDIDATE, V16_CANDIDATE_SHA), "same_candidate_as_stage_s": True},
        "baseline": baseline,
        "previous_1p6": previous,
        "treatment": treatment,
        "metric": {"downforce_absolute": 0.005, "drag_relative": 0.02, "comparison": "adjacent +1.6 m -> +3.2 m"},
        "budget": {"max_new_runs": 1, "mesh_levels": ["V1"], "v2_runs": 0, "v3_runs": 0},
        "artifacts": artifacts,
        "stop_conditions": ["any pinned hash or candidate mismatch", "failed clearance or mesh profile gate", "failed solver convergence or force stationarity", "adjacent transition beyond either registered bound keeps S2 blocked", "a passing transition does not establish grid-independent or absolute downforce"],
        "claims_not_supported": ["grid-independent or absolute Stage V downforce", "reduced-basis FD qualification or shape update", "full-vehicle or high-Re FSAE qualification"],
        "execution": {"solver_started": False, "mesh_generation_started": False, "optimization_campaign_started": False, "new_run_count": 0},
    }
    run_digest = _write_immutable(RUN_MANIFEST, run_document)
    parent = {
        "kind": "stage_v_v16_domain_continuation_3p2_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": run_digest},
        "question": run_document["question"],
        "candidate": run_document["candidate"],
        "baseline": baseline,
        "previous_1p6": previous,
        "treatment": treatment,
        "metric": run_document["metric"],
        "budget": run_document["budget"],
        "claims_not_supported": run_document["claims_not_supported"],
    }
    parent_digest = _write_immutable(PARENT_MANIFEST, parent)
    print(json.dumps({"run_manifest": _rel(RUN_MANIFEST), "run_manifest_sha256": run_digest, "manifest": _rel(PARENT_MANIFEST), "manifest_sha256": parent_digest}, ensure_ascii=False))
    return run_document


def _verify(manifest: dict[str, Any]) -> None:
    if manifest.get("status") != "registered_not_run":
        raise SystemExit("v16 +3.2 contract is not registered_not_run")
    for key, ref in manifest["artifacts"].items():
        if _sha256(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"registered artifact changed: {key}")
    if _sha256(RUN_MANIFEST) != RUN_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("+3.2 run-manifest sidecar mismatch")


def run(manifest: dict[str, Any], timeout: int) -> dict[str, Any]:
    _configure_base()
    _verify(manifest)
    spec = load_problem_spec(EXT_SPEC)
    extension_token = f"{EXTENSION_M:g}".replace(".", "p")
    if extension_token not in spec.problem_id:
        raise SystemExit(
            "the registered +3.2 m ProblemSpec identity is stale: "
            f"{spec.problem_id!r} does not contain {extension_token!r}"
        )
    qualification_path = CASE_DIR / "stage_v_qualification.json"
    if qualification_path.is_file() and _load(qualification_path).get("qualified"):
        base._verify_case_metadata(CASE_DIR, spec)
        return {"case_dir": _rel(CASE_DIR), **_responses(_load(qualification_path))}
    base._clean_case_outputs(CASE_DIR)
    config = problem_spec_to_project_config(spec, candidate_stl=CANDIDATE, voxel_size_m=V1_VOXEL_M)
    mesh_log = CASE_DIR / "log.checkMesh"
    solve_log = CASE_DIR / "log.simpleFoam"
    if not mesh_log.exists():
        preflight = evaluate_stage_v_domain_preflight(spec, CANDIDATE, V1_VOXEL_M)
        if not preflight.qualified:
            raise SystemExit(f"v16 +3.2 preflight failed: {preflight.reasons}")
        write_stage_v_domain_preflight_report(CASE_DIR, preflight)
        generate_openfoam_case(config, base.v16.pq2._declared_domain_bundle(config), CASE_DIR)
        base._verify_case_metadata(CASE_DIR, spec)
        base.v16._patch_location_in_mesh(CASE_DIR)
        (CASE_DIR / "location_in_mesh_patch.json").write_text(json.dumps({"source_case": _rel(BASELINE_CASE), "location_in_mesh": list(base.v16._baseline_location())}, indent=2) + "\n", encoding="utf-8")
        (CASE_DIR / "Allrun").write_text(MESH_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        result = run_openfoam_case(CASE_DIR, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=OPENFOAM_IMAGE)
        if getattr(result, "returncode", None) != 0:
            raise SystemExit("v16 +3.2 mesh run failed")
    check_mesh = evaluate_check_mesh(mesh_log.read_text(encoding="utf-8", errors="ignore"), STAGE_V_QUALIFICATION_PROFILE_V1)
    _write_stagev_level_preflight(CASE_DIR, "stage_s_v16", "V1", V1_VOXEL_M, check_mesh, False, str(STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"]))
    if not check_mesh["qualified"]:
        raise SystemExit(f"v16 +3.2 checkMesh failed: {check_mesh['reasons']}")
    if not solve_log.exists():
        (CASE_DIR / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        result = run_openfoam_case(CASE_DIR, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=OPENFOAM_IMAGE)
        if getattr(result, "returncode", None) != 0:
            raise SystemExit("v16 +3.2 solve run failed")
    write_stage_v_qualification(CASE_DIR, STAGE_V_QUALIFICATION_PROFILE_V1)
    return {"case_dir": _rel(CASE_DIR), **_responses(_load(qualification_path))}


def judge() -> dict[str, Any]:
    if EVIDENCE.exists():
        raise SystemExit("v16 +3.2 evidence already exists; refuse overwrite")
    manifest = _load(RUN_MANIFEST)
    _verify(manifest)
    treatment = _responses(_load(CASE_DIR / "stage_v_qualification.json"))
    previous = manifest["previous_1p6"]
    delta_downforce = treatment["downforce"] - previous["downforce"]
    relative_cd = (treatment["Cd"] - previous["Cd"]) / previous["Cd"]
    metric = manifest["metric"]
    within = treatment["qualified"] and abs(delta_downforce) <= metric["downforce_absolute"] and abs(relative_cd) <= metric["drag_relative"]
    decision = (
        "v16 +1.6 m to +3.2 m transition is within the registered band; stop domain ladder, register the settled reference, and keep S2 as a separate local-FD decision"
        if within
        else "v16 +1.6 m to +3.2 m transition remains outside the registered band; stop domain-only expansion and register a physically justified far-field contract while keeping S2 blocked"
    )
    evidence = {
        "kind": "stage_v_v16_domain_continuation_3p2",
        "schema_version": 1,
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": _sha256(RUN_MANIFEST)},
        "candidate_sha256": V16_CANDIDATE_SHA,
        "previous_1p6": previous,
        "treatment_3p2": treatment,
        "delta_from_previous": {"downforce": delta_downforce, "relative_Cd_change": relative_cd, "downforce_beyond_bound": abs(delta_downforce) > metric["downforce_absolute"], "drag_beyond_bound": abs(relative_cd) > metric["drag_relative"]},
        "decision": decision,
        "summary": {"qualified": treatment["qualified"], "adjacent_transition_within_bound": within, "stage_s_s2_allowed": False},
        "claims_supported": ["one same-candidate v16 V1 +3.2 m domain continuation was compared with the registered +1.6 m treatment"],
        "claims_not_supported": ["grid-independent or absolute Stage V downforce", "Stage S S2 qualification", "shape update or optimization authorization"],
    }
    digest = _write_immutable(EVIDENCE, evidence)
    print(json.dumps({"evidence": _rel(EVIDENCE), "sha256": digest, "decision": decision}, ensure_ascii=False))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="same-candidate v16 Stage V +3.2 m continuation")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.run:
        manifest = _load(RUN_MANIFEST)
        work_f = _load(base.v16.WORK_F_MANIFEST)
        print(json.dumps(run(manifest, int(work_f["solver_budget"]["solver_timeout_seconds"])), ensure_ascii=False))
    elif args.judge:
        judge()
    else:
        parser.error("specify --register, --run or --judge")


if __name__ == "__main__":
    main()
