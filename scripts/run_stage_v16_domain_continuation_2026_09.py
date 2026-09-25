#!/usr/bin/env python3
"""Run the next same-candidate v16 far-field domain continuation.

The v16 V1 factor screen showed large sensitivity to both the registered
domain extension and the top-boundary treatment.  This contract isolates one
physically interpretable question before any reduced-basis flow campaign:
does extending the original box by 1.6 m, while retaining the registered
symmetry/freestream/wall boundary semantics, make the adjacent response
transition from the already-run +0.8 m box small enough to use as a numerical
reference?  It is one new solver case and never authorizes S2 or a shape step.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_v16_domain_boundary_contract_2026_09 as v16  # noqa: E402
from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import (  # noqa: E402
    STAGE_V_QUALIFICATION_PROFILE_V1,
    evaluate_check_mesh,
    write_stage_v_qualification,
)
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256  # noqa: E402
from cfd_sdf.stage_v_domain_preflight import (  # noqa: E402
    evaluate_stage_v_domain_preflight,
    write_stage_v_domain_preflight_report,
)
from stage_t_filtered_ramp import (  # noqa: E402
    MESH_ONLY_ALLRUN,
    SOLVE_ONLY_ALLRUN,
    _write_stagev_level_preflight,
)


CONTINUATION_M = 1.6
OUT_ROOT = ROOT / "work/stage_v_v16_domain_continuation_2026_09"
SPEC_ROOT = OUT_ROOT / "specs"
EXT_SPEC = SPEC_ROOT / "project_matched_re_laminar_domain_extended_1p6_v2.yaml"
EXT_DOMAIN_STL = SPEC_ROOT / "geometry/design_domain.stl"
CASE_DIR = OUT_ROOT / "far_field_domain_extension_1p6/V1"

PARENT_MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_continuation_manifest_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_continuation_run_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_v16_domain_continuation_2026_09.json"
LINEAGE_AUDIT = ROOT / "docs/evidence/stage_v_v16_domain_boundary_lineage_audit_2026_09.json"

V1_VOXEL_M = v16.V1_VOXEL_M
CANDIDATE = v16.CANDIDATE
BASE_SPEC = v16.BASE_SPEC
BASELINE_CASE = v16.BASELINE_CASE
ADJACENT_CASE = v16.EXT_CASE
V16_CANDIDATE_SHA = v16.V16_CANDIDATE_SHA
OPENFOAM_IMAGE = v16.OPENFOAM_IMAGE


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"required file is missing: {_rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


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


def _artifact(path: Path, expected: str | None = None) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"required artifact is missing: {_rel(path)}")
    observed = _sha256(path)
    if expected is not None and observed != expected:
        raise SystemExit(f"hash mismatch for {_rel(path)}: expected {expected}, observed {observed}")
    return {"path": _rel(path), "sha256": observed}


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


def _extended_spec_document() -> dict[str, Any]:
    raw = yaml.safe_load(BASE_SPEC.read_text(encoding="utf-8"))
    extended = copy.deepcopy(raw)
    bounds = raw["grid"]["domain_bounds_m"]
    extension_label = f"{CONTINUATION_M:g}".replace(".", "p")
    extended["problem_id"] = f"stage_sv_laminar_matched_re_domain_{extension_label}_v2"
    extended["grid"]["domain_bounds_m"] = {
        "lower": [
            float(bounds["lower"][0]) - CONTINUATION_M,
            float(bounds["lower"][1]) - CONTINUATION_M,
            float(bounds["lower"][2]),
        ],
        "upper": [
            float(bounds["upper"][0]) + CONTINUATION_M,
            float(bounds["upper"][1]) + CONTINUATION_M,
            float(bounds["upper"][2]) + CONTINUATION_M,
        ],
    }
    return extended


def _ensure_inputs() -> dict[str, Any]:
    document = _extended_spec_document()
    SPEC_ROOT.mkdir(parents=True, exist_ok=True)
    if EXT_SPEC.exists():
        if yaml.safe_load(EXT_SPEC.read_text(encoding="utf-8")) != document:
            raise SystemExit("the v16 continuation ProblemSpec differs from the registered construction")
    else:
        EXT_SPEC.write_text(yaml.safe_dump(document, sort_keys=False, default_flow_style=False), encoding="utf-8")
    EXT_DOMAIN_STL.parent.mkdir(parents=True, exist_ok=True)
    source_hash = _sha256(v16.DOMAIN_STL)
    if EXT_DOMAIN_STL.exists():
        if _sha256(EXT_DOMAIN_STL) != source_hash:
            raise SystemExit("the staged continuation design-domain STL differs from its source")
    else:
        shutil.copyfile(v16.DOMAIN_STL, EXT_DOMAIN_STL)
    spec = load_problem_spec(EXT_SPEC)
    raw = yaml.safe_load(BASE_SPEC.read_text(encoding="utf-8"))
    diff_keys = sorted(key for key in set(raw) | set(document) if raw.get(key) != document.get(key))
    if diff_keys != ["grid", "problem_id"]:
        raise SystemExit(f"continuation spec differs beyond domain and problem_id: {diff_keys}")
    return {
        "path": _rel(EXT_SPEC),
        "sha256": _sha256(EXT_SPEC),
        "canonical_sha256": problem_spec_sha256(spec),
        "problem_id": spec.problem_id,
        "diff_keys": diff_keys,
        "lower_m": list(spec.grid.domain_bounds_m.lower),
        "upper_m": list(spec.grid.domain_bounds_m.upper),
        "extension_m": CONTINUATION_M,
        "staged_design_domain": _artifact(EXT_DOMAIN_STL, source_hash),
    }


def _verify_case_metadata(case_dir: Path, spec: Any) -> None:
    metadata_path = case_dir / "case_metadata.json"
    if not metadata_path.is_file():
        raise SystemExit(f"generated case metadata is missing: {_rel(metadata_path)}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_hash = problem_spec_sha256(spec)
    if metadata.get("problem_id") != spec.problem_id:
        raise SystemExit(
            "generated case metadata problem_id does not match the registered ProblemSpec: "
            f"{metadata.get('problem_id')!r} != {spec.problem_id!r}"
        )
    if metadata.get("problem_spec_sha256") != expected_hash:
        raise SystemExit(
            "generated case metadata problem_spec_sha256 does not match the registered ProblemSpec: "
            f"{metadata.get('problem_spec_sha256')!r} != {expected_hash!r}"
        )


def register() -> dict[str, Any]:
    if any(path.exists() for path in (PARENT_MANIFEST, RUN_MANIFEST, EVIDENCE)):
        raise SystemExit("v16 domain continuation artifacts already exist; refuse overwrite")
    factor_manifest = _load(v16.MANIFEST)
    factor_evidence = _load(v16.EVIDENCE)
    lineage = _load(LINEAGE_AUDIT)
    if factor_evidence.get("decision") != "v16 factor response remains outside the registered band; keep S2 blocked and register a revised contract":
        raise SystemExit("the v16 factor screen does not authorize a continuation")
    if lineage.get("status") != "pass":
        raise SystemExit("v16 factor lineage audit did not pass")
    if _sha256(CANDIDATE) != V16_CANDIDATE_SHA:
        raise SystemExit("the registered v16 candidate STL changed")
    baseline_qualification = _load(BASELINE_CASE / "stage_v_qualification.json")
    adjacent_qualification = _load(ADJACENT_CASE / "stage_v_qualification.json")
    if not baseline_qualification.get("qualified") or not adjacent_qualification.get("qualified"):
        raise SystemExit("baseline and adjacent v16 qualifications must both be profile-qualified")
    inputs = _ensure_inputs()
    baseline = {"case_dir": _rel(BASELINE_CASE), **_responses(baseline_qualification)}
    adjacent = {"case_dir": _rel(ADJACENT_CASE), **_responses(adjacent_qualification)}
    treatment = {
        "name": "far_field_domain_extension_1p6",
        "factor": "far-field domain size",
        "change": "extend inlet, outlet, sideMin, sideMax, and top by 1.6 m from the original v16 V1 box; bottom remains at z=-0.6 m",
        "far_field_faces": list(v16.FAR_FIELD_FACES),
        "ground_face": v16.GROUND_FACE,
        "boundary_contract": factor_manifest["common_conditions"]["boundary_contract"],
        "extended_spec": inputs,
        "case_dir": _rel(CASE_DIR),
    }
    common_artifacts = {
        _rel(v16.MANIFEST): _artifact(v16.MANIFEST),
        _rel(v16.EVIDENCE): _artifact(v16.EVIDENCE),
        _rel(LINEAGE_AUDIT): _artifact(LINEAGE_AUDIT),
        _rel(CANDIDATE): _artifact(CANDIDATE, V16_CANDIDATE_SHA),
        _rel(BASE_SPEC): _artifact(BASE_SPEC),
        _rel(v16.DOMAIN_STL): _artifact(v16.DOMAIN_STL),
        _rel(BASELINE_CASE / "stage_v_qualification.json"): _artifact(BASELINE_CASE / "stage_v_qualification.json"),
        _rel(ADJACENT_CASE / "stage_v_qualification.json"): _artifact(ADJACENT_CASE / "stage_v_qualification.json"),
        _rel(EXT_SPEC): _artifact(EXT_SPEC),
        _rel(EXT_DOMAIN_STL): _artifact(EXT_DOMAIN_STL),
        _rel(Path(__file__)): _artifact(Path(__file__)),
    }
    run_document = {
        "kind": "stage_v_v16_domain_continuation_run_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "evidence_class": "contract",
        "question": "Does the same-candidate v16 response settle when the original V1 domain is extended by 1.6 m under unchanged symmetry/freestream/wall boundary semantics?",
        "parent_factor_manifest": _artifact(v16.MANIFEST),
        "parent_factor_evidence": _artifact(v16.EVIDENCE),
        "lineage_audit": _artifact(LINEAGE_AUDIT),
        "candidate": {"stl": _artifact(CANDIDATE, V16_CANDIDATE_SHA), "same_candidate_as_stage_s": True},
        "baseline": baseline,
        "adjacent_0p8": adjacent,
        "treatment": treatment,
        "metric": {"downforce_absolute": 0.005, "drag_relative": 0.02, "comparison": "adjacent +0.8 m -> +1.6 m"},
        "budget": {"max_new_runs": 1, "mesh_levels": ["V1"], "v2_runs": 0, "v3_runs": 0},
        "artifacts": common_artifacts,
        "stop_conditions": [
            "any pinned hash mismatch or candidate identity mismatch",
            "failed stage_v_clearance_v1 or stage_v_qualification_v1 mesh gate",
            "failed solver convergence or force stationarity",
            "adjacent transition beyond either registered bound keeps S2 blocked",
            "a passing transition does not establish grid-independent or absolute downforce",
        ],
        "claims_not_supported": [
            "grid-independent or absolute Stage V downforce",
            "reduced-basis FD qualification or shape update",
            "full-vehicle or high-Re FSAE qualification",
        ],
        "execution": {"solver_started": False, "mesh_generation_started": False, "optimization_campaign_started": False, "new_run_count": 0},
    }
    digest = _write_immutable(RUN_MANIFEST, run_document)
    parent = {
        "kind": "stage_v_v16_domain_continuation_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": digest},
        "question": run_document["question"],
        "candidate": run_document["candidate"],
        "baseline": baseline,
        "adjacent_0p8": adjacent,
        "treatment": treatment,
        "metric": run_document["metric"],
        "budget": run_document["budget"],
        "claims_not_supported": run_document["claims_not_supported"],
    }
    parent_digest = _write_immutable(PARENT_MANIFEST, parent)
    print(json.dumps({"run_manifest": _rel(RUN_MANIFEST), "run_manifest_sha256": digest, "manifest": _rel(PARENT_MANIFEST), "manifest_sha256": parent_digest}, ensure_ascii=False))
    return run_document


def _verify(manifest: dict[str, Any]) -> None:
    if manifest.get("status") != "registered_not_run":
        raise SystemExit("v16 continuation is not in registered_not_run state")
    for key, ref in manifest["artifacts"].items():
        if _sha256(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"registered artifact changed: {key}")
    if _sha256(RUN_MANIFEST) != RUN_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("v16 continuation run-manifest sidecar mismatch")


def _clean_case_outputs(case_dir: Path) -> None:
    if not case_dir.exists():
        return
    for child in list(case_dir.iterdir()):
        if child.is_dir() and child.name not in {"0", "constant", "system"}:
            shutil.rmtree(child)
        elif child.is_file() and child.name.startswith(("log.", "openfoam_run", "stage_v_", "location_in_mesh")):
            child.unlink()


def run(manifest: dict[str, Any], timeout: int) -> dict[str, Any]:
    _verify(manifest)
    spec = load_problem_spec(EXT_SPEC)
    qualification_path = CASE_DIR / "stage_v_qualification.json"
    if qualification_path.is_file() and _load(qualification_path).get("qualified"):
        _verify_case_metadata(CASE_DIR, spec)
        return {"case_dir": _rel(CASE_DIR), **_responses(_load(qualification_path))}
    _clean_case_outputs(CASE_DIR)
    config = problem_spec_to_project_config(spec, candidate_stl=CANDIDATE, voxel_size_m=V1_VOXEL_M)
    mesh_log = CASE_DIR / "log.checkMesh"
    solve_log = CASE_DIR / "log.simpleFoam"
    if not mesh_log.exists():
        preflight = evaluate_stage_v_domain_preflight(spec, CANDIDATE, V1_VOXEL_M)
        if not preflight.qualified:
            raise SystemExit(f"v16 continuation preflight failed: {preflight.reasons}")
        write_stage_v_domain_preflight_report(CASE_DIR, preflight)
        generate_openfoam_case(config, v16.pq2._declared_domain_bundle(config), CASE_DIR)
        _verify_case_metadata(CASE_DIR, spec)
        v16._patch_location_in_mesh(CASE_DIR)
        (CASE_DIR / "location_in_mesh_patch.json").write_text(json.dumps({"source_case": _rel(BASELINE_CASE), "location_in_mesh": list(v16._baseline_location())}, indent=2) + "\n", encoding="utf-8")
        (CASE_DIR / "Allrun").write_text(MESH_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        run_result = run_openfoam_case(CASE_DIR, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=OPENFOAM_IMAGE)
        if getattr(run_result, "returncode", None) != 0:
            raise SystemExit("v16 continuation mesh run failed")
    check_mesh = evaluate_check_mesh(mesh_log.read_text(encoding="utf-8", errors="ignore"), STAGE_V_QUALIFICATION_PROFILE_V1)
    _write_stagev_level_preflight(CASE_DIR, "stage_s_v16", "V1", V1_VOXEL_M, check_mesh, False, str(STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"]))
    if not check_mesh["qualified"]:
        raise SystemExit(f"v16 continuation checkMesh failed: {check_mesh['reasons']}")
    if not solve_log.exists():
        (CASE_DIR / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        run_result = run_openfoam_case(CASE_DIR, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=OPENFOAM_IMAGE)
        if getattr(run_result, "returncode", None) != 0:
            raise SystemExit("v16 continuation solve run failed")
    write_stage_v_qualification(CASE_DIR, STAGE_V_QUALIFICATION_PROFILE_V1)
    return {"case_dir": _rel(CASE_DIR), **_responses(_load(qualification_path))}


def judge() -> dict[str, Any]:
    if EVIDENCE.exists():
        raise SystemExit("v16 continuation evidence already exists; refuse overwrite")
    manifest = _load(RUN_MANIFEST)
    _verify(manifest)
    result = _load(CASE_DIR / "stage_v_qualification.json")
    treatment = _responses(result)
    previous = manifest["adjacent_0p8"]
    delta_downforce = treatment["downforce"] - previous["downforce"]
    relative_cd = (treatment["Cd"] - previous["Cd"]) / previous["Cd"]
    metric = manifest["metric"]
    within = treatment["qualified"] and abs(delta_downforce) <= metric["downforce_absolute"] and abs(relative_cd) <= metric["drag_relative"]
    decision = (
        "v16 +0.8 m to +1.6 m transition is within the registered band; keep S2 blocked until the boundary contract is reconciled and re-register the Stage S reference"
        if within
        else "v16 domain response remains moving beyond the registered band; register the next continuation or a physically justified far-field contract and keep S2 blocked"
    )
    evidence = {
        "kind": "stage_v_v16_domain_continuation",
        "schema_version": 1,
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": _sha256(RUN_MANIFEST)},
        "candidate_sha256": V16_CANDIDATE_SHA,
        "previous_extension_0p8": previous,
        "treatment_1p6": treatment,
        "delta_from_previous": {
            "downforce": delta_downforce,
            "relative_Cd_change": relative_cd,
            "downforce_beyond_bound": abs(delta_downforce) > metric["downforce_absolute"],
            "drag_beyond_bound": abs(relative_cd) > metric["drag_relative"],
        },
        "decision": decision,
        "summary": {"qualified": treatment["qualified"], "adjacent_transition_within_bound": within, "stage_s_s2_allowed": False},
        "claims_supported": ["one same-candidate v16 V1 domain continuation was compared with the corrected +0.8 m treatment"],
        "claims_not_supported": ["grid-independent or absolute Stage V downforce", "Stage S S2 qualification", "shape update or optimization authorization"],
    }
    digest = _write_immutable(EVIDENCE, evidence)
    print(json.dumps({"evidence": _rel(EVIDENCE), "sha256": digest, "decision": decision}, ensure_ascii=False))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="same-candidate v16 Stage V domain continuation")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
        return
    if args.judge:
        judge()
        return
    if args.run:
        manifest = _load(RUN_MANIFEST)
        work_f = _load(v16.WORK_F_MANIFEST)
        print(json.dumps(run(manifest, int(work_f["solver_budget"]["solver_timeout_seconds"])), ensure_ascii=False))
        return
    parser.error("specify --register, --run or --judge")


if __name__ == "__main__":
    main()
