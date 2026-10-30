"""Registered Stage V domain-continuation campaign after the PQ2 No-Go.

This campaign changes only the far-field domain size.  It keeps the candidate,
V2 voxel size, laminar operating point, symmetry boundaries, force
normalization, and qualification profile fixed.  The already-run +0.8 m
extension is the adjacent reference; this run tests a +1.6 m extension from
the original fixed domain.

The campaign is deliberately one treatment and one new OpenFOAM run.  A
passing adjacent transition is a candidate-specific numerical band, not a
grid-independent downforce reference.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_v_domain_boundary_factor_2026_09 as pq2  # noqa: E402
from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import (  # noqa: E402
    STAGE_V_QUALIFICATION_PROFILE_V1,
    evaluate_check_mesh,
    write_stage_v_qualification,
)
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
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
ROOT_OUT = ROOT / "work/stage_v_domain_continuation_2026_09"
EXT_SPEC = ROOT_OUT / "specs/project_matched_re_laminar_domain_extended_1p6_v1.yaml"
CASE_DIR = ROOT_OUT / "far_field_domain_extension_1p6/V2"
MANIFEST = ROOT / "docs/evidence/stage_v_domain_continuation_manifest_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_domain_continuation_run_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_domain_continuation_2026_09.json"
PQ2_EVIDENCE = ROOT / "docs/evidence/stage_v_domain_boundary_factor_2026_09.json"
PQ2_RUN_MANIFEST = ROOT / "docs/evidence/stage_v_domain_boundary_factor_run_manifest_2026_09.json"
PREVIOUS_CASE = ROOT / "work/stage_v_domain_boundary_factor_2026_09/far_field_domain_extension/V2"
PREVIOUS_QUALIFICATION = PREVIOUS_CASE / "stage_v_qualification.json"
V2_VOXEL_M = pq2.V2_VOXEL_M
CID = pq2.CID
LEVEL = pq2.LEVEL


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _extended_spec() -> dict:
    raw = yaml.safe_load(pq2.SPEC.read_text(encoding="utf-8"))
    extended = copy.deepcopy(raw)
    bounds = raw["grid"]["domain_bounds_m"]
    # Keep the v2 identifier below the schema's 64-character limit.
    extended["problem_id"] = "stage_sv_laminar_matched_re_domain_1p6_v1"
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


def _ensure_extended_spec() -> dict:
    extended = _extended_spec()
    EXT_SPEC.parent.mkdir(parents=True, exist_ok=True)
    if EXT_SPEC.exists():
        existing = yaml.safe_load(EXT_SPEC.read_text(encoding="utf-8"))
        if existing != extended:
            raise SystemExit("the existing continuation spec is not deterministic")
    else:
        EXT_SPEC.write_text(
            yaml.safe_dump(extended, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    _ensure_geometry_reference()
    spec = load_problem_spec(EXT_SPEC)
    return {
        "path": str(EXT_SPEC.relative_to(ROOT)),
        "sha256": _sha256(EXT_SPEC),
        "lower_m": list(spec.grid.domain_bounds_m.lower),
        "upper_m": list(spec.grid.domain_bounds_m.upper),
        "extension_m": CONTINUATION_M,
    }


def _ensure_geometry_reference() -> dict:
    """Stage the relative design-domain STL beside the copied ProblemSpec."""
    source = pq2.SPEC.parent / "geometry" / "design_domain.stl"
    destination = EXT_SPEC.parent / "geometry" / "design_domain.stl"
    if not source.is_file():
        raise SystemExit(f"base design-domain STL is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hash = _sha256(source)
    if destination.exists():
        if _sha256(destination) != source_hash:
            raise SystemExit("the staged design-domain STL differs from the base spec")
    else:
        shutil.copyfile(source, destination)
    return {
        "source_path": str(source.relative_to(ROOT)),
        "staged_path": str(destination.relative_to(ROOT)),
        "sha256": source_hash,
    }


def register() -> dict:
    if RUN_MANIFEST.exists():
        raise SystemExit("continuation run manifest already exists; refuse overwrite")
    if MANIFEST.exists():
        raise SystemExit("continuation manifest already exists; refuse overwrite")
    pq2_evidence = ca.load_json(PQ2_EVIDENCE)
    if pq2_evidence["decision"] != (
        "register the moving factor(s) and rerun the family: "
        "far_field_domain_extension, top_pressure_outlet"
    ):
        raise SystemExit("the PQ2 No-Go evidence does not authorize this continuation")
    if not PREVIOUS_QUALIFICATION.is_file():
        raise SystemExit("the adjacent +0.8 m qualification is missing")
    previous = ca.load_json(PREVIOUS_QUALIFICATION)
    if not previous.get("qualified"):
        raise SystemExit("the adjacent +0.8 m treatment is not qualified")
    base = pq2._baseline_record()
    if not base["qualified"]:
        raise SystemExit("the fixed-domain baseline is not qualified")
    extended = _ensure_extended_spec()
    manifest = {
        "kind": "stage_v_domain_continuation_run_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "question": (
            "Does a second far-field extension with the same V2 mesh and "
            "symmetry boundaries make the adjacent downforce transition "
            "smaller than the registered candidate-specific bound?"
        ),
        "parent_pq2_evidence": {
            "path": str(PQ2_EVIDENCE.relative_to(ROOT)),
            "sha256": _sha256(PQ2_EVIDENCE),
        },
        "parent_run_manifest": {
            "path": str(PQ2_RUN_MANIFEST.relative_to(ROOT)),
            "sha256": _sha256(PQ2_RUN_MANIFEST),
        },
        "candidate": {
            "case_id": CID,
            "stl": {
                "path": str(pq2.CANDIDATE.relative_to(ROOT)),
                "sha256": _sha256(pq2.CANDIDATE),
            },
        },
        "base_spec": {
            "path": str(pq2.SPEC.relative_to(ROOT)),
            "sha256": _sha256(pq2.SPEC),
        },
        "baseline_fixed_domain": base,
        "previous_extension": {
            "name": "far_field_domain_extension_0p8",
            "case_dir": str(PREVIOUS_CASE.relative_to(ROOT)),
            "qualification_path": str(PREVIOUS_QUALIFICATION.relative_to(ROOT)),
            "qualification_sha256": _sha256(PREVIOUS_QUALIFICATION),
            "qualified": bool(previous.get("qualified")),
            "cells": int(previous["check_mesh"]["total_cells"]),
            "iterations": previous["solver"].get("iteration_count"),
            "Cd": float(previous["force_stationarity"]["responses"]["Cd"]["mean"]),
            "downforce": float(
                previous["force_stationarity"]["responses"]["downforce"]["mean"]
            ),
        },
        "treatment": {
            "name": "far_field_domain_extension_1p6",
            "factor": "far-field domain size",
            "domain_change": (
                "extend inlet, outlet, sideMin, sideMax, and top by 1.6 m "
                "from the original fixed-domain box; bottom remains z=-0.6 m"
            ),
            "far_field_faces": list(pq2.FAR_FIELD_FACES),
            "ground_face": pq2.GROUND_FACE,
            "extended_spec": extended,
            "voxel_size_m": V2_VOXEL_M,
            "boundary_contract": {
                "top": "symmetryPlane",
                "sideMin": "symmetryPlane",
                "sideMax": "symmetryPlane",
                "bottom": "wall",
                "inlet": "freestream",
                "outlet": "pressure_outlet",
            },
            "case_dir": str(CASE_DIR.relative_to(ROOT)),
        },
        "metric": {
            "downforce_absolute": 0.005,
            "drag_relative": 0.02,
            "comparison": "adjacent extension 0.8 m -> 1.6 m",
        },
        "stop_conditions": [
            "reject if the treatment is not qualified",
            "if either adjacent metric exceeds its registered bound, do not start S2",
            "a passing adjacent transition is not a grid-independent claim",
        ],
        "budget": {"max_new_runs": 1, "v3_runs": 0},
        "claims_not_supported": [
            "no grid-independent downforce reference",
            "no full-vehicle or high-Re qualification",
            "no Stage S shape update authorization",
        ],
    }
    parent_manifest = {
        "kind": "stage_v_domain_continuation_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "question": manifest["question"],
        "candidate": manifest["candidate"],
        "base_spec": manifest["base_spec"],
        "baseline_fixed_domain": manifest["baseline_fixed_domain"],
        "previous_extension": manifest["previous_extension"],
        "treatment": manifest["treatment"],
        "metric": manifest["metric"],
        "stop_conditions": manifest["stop_conditions"],
        "budget": manifest["budget"],
        "claims_not_supported": manifest["claims_not_supported"],
    }
    MANIFEST.write_text(
        json.dumps(parent_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest["parent_manifest"] = {
        "path": str(MANIFEST.relative_to(ROOT)),
        "sha256": _sha256(MANIFEST),
    }
    RUN_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"path": str(RUN_MANIFEST.relative_to(ROOT)), "sha256": _sha256(RUN_MANIFEST)}, indent=2))
    return manifest


def _verify(manifest: dict) -> None:
    for key in ("parent_manifest", "parent_pq2_evidence", "parent_run_manifest", "base_spec"):
        record = manifest[key]
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"registered input changed: {key}")
    candidate = manifest["candidate"]["stl"]
    if _sha256(ROOT / candidate["path"]) != candidate["sha256"]:
        raise SystemExit("registered candidate STL changed")
    baseline_hash = manifest["baseline_fixed_domain"]["qualification_sha256"]
    if _sha256(pq2.BASELINE_CASE / "stage_v_qualification.json") != baseline_hash:
        raise SystemExit("fixed-domain baseline qualification changed")
    previous = manifest["previous_extension"]
    if _sha256(ROOT / previous["qualification_path"]) != previous["qualification_sha256"]:
        raise SystemExit("adjacent extension qualification changed")


def run_continuation(manifest: dict, timeout: int, image: str) -> dict:
    treatment = manifest["treatment"]
    qualification_path = CASE_DIR / "stage_v_qualification.json"
    mesh_log = CASE_DIR / "log.checkMesh"
    solve_log = CASE_DIR / "log.simpleFoam"
    if qualification_path.exists() and ca.load_json(qualification_path).get("qualified"):
        return {"case_dir": treatment["case_dir"], **_responses(ca.load_json(qualification_path))}
    if solve_log.exists():
        solve_log.unlink()
        for child in list(CASE_DIR.iterdir()):
            if child.is_dir() and child.name not in {"0", "constant", "system"}:
                shutil.rmtree(child)
    _ensure_geometry_reference()
    spec = load_problem_spec(EXT_SPEC)
    config = pq2.problem_spec_to_project_config(
        spec, candidate_stl=pq2.CANDIDATE, voxel_size_m=V2_VOXEL_M
    )
    if not mesh_log.exists():
        preflight = evaluate_stage_v_domain_preflight(spec, pq2.CANDIDATE, V2_VOXEL_M)
        if not preflight.qualified:
            raise SystemExit(f"continuation domain preflight failed: {preflight.reasons}")
        write_stage_v_domain_preflight_report(CASE_DIR, preflight)
        pq2.generate_openfoam_case(config, pq2._declared_domain_bundle(config), CASE_DIR)
        location_patch = pq2._reuse_baseline_location_in_mesh(CASE_DIR)
        (CASE_DIR / "location_in_mesh_patch.json").write_text(
            json.dumps(location_patch, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (CASE_DIR / "Allrun").write_text(MESH_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        run = run_openfoam_case(
            CASE_DIR, backend="docker", dry_run=False, timeout_seconds=7200, docker_image=image
        )
        if getattr(run, "returncode", None) != 0:
            raise SystemExit("continuation mesh run failed")
    check_mesh = evaluate_check_mesh(
        mesh_log.read_text(encoding="utf-8", errors="ignore"),
        STAGE_V_QUALIFICATION_PROFILE_V1,
    )
    _write_stagev_level_preflight(
        CASE_DIR,
        CID,
        LEVEL,
        V2_VOXEL_M,
        check_mesh,
        False,
        str(STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"]),
    )
    if not check_mesh["qualified"]:
        raise SystemExit(f"continuation checkMesh failed: {check_mesh['reasons']}")
    (CASE_DIR / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
    run = run_openfoam_case(
        CASE_DIR, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=image
    )
    if getattr(run, "returncode", None) != 0:
        raise SystemExit("continuation solve run failed")
    write_stage_v_qualification(CASE_DIR, STAGE_V_QUALIFICATION_PROFILE_V1)
    qualification = ca.load_json(qualification_path)
    return {"case_dir": treatment["case_dir"], **_responses(qualification)}


def _responses(qualification: dict) -> dict:
    responses = qualification["force_stationarity"]["responses"]
    return {
        "qualified": bool(qualification.get("qualified")),
        "reasons": list(qualification.get("reasons", [])),
        "cells": int(qualification["check_mesh"]["total_cells"]),
        "iterations": qualification["solver"].get("iteration_count"),
        "Cd": float(responses["Cd"]["mean"]),
        "downforce": float(responses["downforce"]["mean"]),
    }


def judge() -> dict:
    if EVIDENCE.exists():
        raise SystemExit("continuation evidence already exists; refuse overwrite")
    manifest = ca.load_json(RUN_MANIFEST)
    _verify(manifest)
    if not CASE_DIR.joinpath("stage_v_qualification.json").is_file():
        raise SystemExit("continuation treatment is not run")
    result = _responses(ca.load_json(CASE_DIR / "stage_v_qualification.json"))
    previous = manifest["previous_extension"]
    delta_downforce = result["downforce"] - previous["downforce"]
    relative_cd = (result["Cd"] - previous["Cd"]) / previous["Cd"]
    bounds = manifest["metric"]
    within = (
        abs(delta_downforce) <= bounds["downforce_absolute"]
        and abs(relative_cd) <= bounds["drag_relative"]
        and result["qualified"]
    )
    decision = (
        "adjacent extension is within the registered bound; register the 1.6 m "
        "domain and re-register the Stage S baseline before S2"
        if within
        else "domain remains moving beyond the registered bound; register the next "
        "domain continuation and keep S2 blocked"
    )
    evidence = {
        "kind": "stage_v_domain_continuation",
        "schema_version": 1,
        "run_manifest": {
            "path": str(RUN_MANIFEST.relative_to(ROOT)),
            "sha256": _sha256(RUN_MANIFEST),
        },
        "previous_extension": previous,
        "treatment": result,
        "delta_from_previous": {
            "downforce": delta_downforce,
            "relative_Cd_change": relative_cd,
            "downforce_beyond_bound": abs(delta_downforce) > bounds["downforce_absolute"],
            "drag_beyond_bound": abs(relative_cd) > bounds["drag_relative"],
        },
        "decision": decision,
        "summary": {
            "qualified": bool(result["qualified"]),
            "adjacent_transition_within_bound": bool(within),
            "v3_runs": 0,
        },
        "claims_supported": [
            "one V2 domain continuation was compared with the qualified +0.8 m treatment",
        ],
        "claims_not_supported": [
            "no grid-independent downforce reference",
            "no Stage S shape update authorization",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    print(decision)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage V domain continuation")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    work_f = ca.load_json(ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json")
    timeout = int(work_f["solver_budget"]["solver_timeout_seconds"])
    image = work_f["openfoam_image"]
    if args.register:
        register()
    elif args.run:
        manifest = ca.load_json(RUN_MANIFEST)
        _verify(manifest)
        print(json.dumps(run_continuation(manifest, timeout, image), indent=2))
    elif args.judge:
        judge()
    else:
        parser.error("specify --register, --run or --judge")


if __name__ == "__main__":
    main()
