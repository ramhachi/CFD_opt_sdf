#!/usr/bin/env python3
"""Register and run the v16-specific Stage V domain/boundary factor screen.

The screen is deliberately separate from the historical PQ2 runner.  It uses
the v16 Stage S candidate and the qualified Work F V1 case as its baseline,
and registers two independent one-factor treatments before any new solver run:

* extend the five far-field faces by 0.8 m while retaining the ground wall;
* change only the top boundary from symmetryPlane to a pressure outlet.

This script never changes the historical PQ2 manifests.  A successful
treatment is a candidate-specific numerical result, not a grid-independent
Stage V reference and not permission to start S2 or a shape update.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

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


AUDIT = ROOT / "docs/evidence/stage_s_v16_contract_audit_manifest_2026_09.json"
WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
BASELINE_MANIFEST = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"
BASELINE_SOLVER_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_v1_solver_2026_09.json"
BASELINE_CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"
BASE_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
CANDIDATE = ROOT / "work/pq4_1_v16_state_v2/sweep/threshold_0.5/iso_surface.stl"
DOMAIN_STL = ROOT / "work/stage_sv_laminar/geometry/design_domain.stl"

OUT_ROOT = ROOT / "work/stage_v_v16_domain_boundary_v2_2026_09"
SPEC_ROOT = OUT_ROOT / "specs"
EXT_SPEC = SPEC_ROOT / "project_matched_re_laminar_domain_extended_0p8_v2.yaml"
EXT_DOMAIN_STL = SPEC_ROOT / "geometry/design_domain.stl"
EXT_CASE = OUT_ROOT / "far_field_domain_extension_0p8/V1"
TOP_CASE = OUT_ROOT / "top_pressure_outlet/V1"

MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_boundary_contract_manifest_v2_2026_09.json"
SIDECAR = MANIFEST.with_suffix(".json.sha256")
EVIDENCE = ROOT / "docs/evidence/stage_v_v16_domain_boundary_contract_v2_2026_09.json"
EVIDENCE_SIDECAR = EVIDENCE.with_suffix(".json.sha256")

V1_VOXEL_M = 0.05
EXTENSION_M = 0.8
FAR_FIELD_FACES = ("inlet", "outlet", "sideMin", "sideMax", "top")
GROUND_FACE = "bottom"
V16_CANDIDATE_SHA = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"
OPENFOAM_IMAGE_ID = "sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _require(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"required file is missing: {_rel(path)}")
    return path


def _artifact(path: Path, expected: str | None = None) -> dict[str, str]:
    _require(path)
    observed = _sha256(path)
    if expected is not None and observed != expected:
        raise SystemExit(f"hash mismatch for {_rel(path)}: expected {expected}, observed {observed}")
    return {"path": _rel(path), "sha256": observed}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(_require(path).read_text(encoding="utf-8"))


def _baseline_record() -> dict[str, Any]:
    qualification = _load(BASELINE_CASE / "stage_v_qualification.json")
    responses = qualification["force_stationarity"]["responses"]
    return {
        "case_dir": _rel(BASELINE_CASE),
        "qualification_path": _rel(BASELINE_CASE / "stage_v_qualification.json"),
        "qualification_sha256": _sha256(BASELINE_CASE / "stage_v_qualification.json"),
        "qualified": bool(qualification.get("qualified")),
        "cells": int(qualification["check_mesh"]["total_cells"]),
        "iterations": qualification["solver"].get("iteration_count"),
        "Cd": float(responses["Cd"]["mean"]),
        "downforce": float(responses["downforce"]["mean"]),
        "raw_check_mesh_mesh_ok": bool(qualification["check_mesh"].get("mesh_ok")),
        "check_mesh_profile_qualified": bool(qualification["check_mesh"].get("qualified")),
    }


def _extended_spec_document() -> dict[str, Any]:
    raw = yaml.safe_load(_require(BASE_SPEC).read_text(encoding="utf-8"))
    extended = copy.deepcopy(raw)
    bounds = raw["grid"]["domain_bounds_m"]
    extended["problem_id"] = "stage_sv_laminar_matched_re_domain_0p8_v2"
    extended["grid"]["domain_bounds_m"] = {
        "lower": [
            float(bounds["lower"][0]) - EXTENSION_M,
            float(bounds["lower"][1]) - EXTENSION_M,
            float(bounds["lower"][2]),
        ],
        "upper": [
            float(bounds["upper"][0]) + EXTENSION_M,
            float(bounds["upper"][1]) + EXTENSION_M,
            float(bounds["upper"][2]) + EXTENSION_M,
        ],
    }
    return extended


def _ensure_extended_inputs() -> dict[str, Any]:
    document = _extended_spec_document()
    SPEC_ROOT.mkdir(parents=True, exist_ok=True)
    if EXT_SPEC.exists():
        if yaml.safe_load(EXT_SPEC.read_text(encoding="utf-8")) != document:
            raise SystemExit("the v16 extended-domain ProblemSpec differs from the registered construction")
    else:
        EXT_SPEC.write_text(yaml.safe_dump(document, sort_keys=False, default_flow_style=False), encoding="utf-8")
    EXT_DOMAIN_STL.parent.mkdir(parents=True, exist_ok=True)
    source_hash = _sha256(_require(DOMAIN_STL))
    if EXT_DOMAIN_STL.exists():
        if _sha256(EXT_DOMAIN_STL) != source_hash:
            raise SystemExit("the v16 staged design-domain STL differs from the registered source")
    else:
        shutil.copyfile(DOMAIN_STL, EXT_DOMAIN_STL)
    spec = load_problem_spec(EXT_SPEC)
    diff_keys = sorted(
        key for key in set(yaml.safe_load(BASE_SPEC.read_text(encoding="utf-8"))) | set(document)
        if yaml.safe_load(BASE_SPEC.read_text(encoding="utf-8")).get(key) != document.get(key)
    )
    if diff_keys != ["grid", "problem_id"]:
        raise SystemExit(f"extended v16 spec differs beyond domain and problem_id: {diff_keys}")
    return {
        "path": _rel(EXT_SPEC),
        "sha256": _sha256(EXT_SPEC),
        "file_sha256": _sha256(EXT_SPEC),
        "canonical_sha256": problem_spec_sha256(spec),
        "diff_keys": diff_keys,
        "lower_m": list(spec.grid.domain_bounds_m.lower),
        "upper_m": list(spec.grid.domain_bounds_m.upper),
        "extension_m": EXTENSION_M,
        "staged_design_domain": _artifact(EXT_DOMAIN_STL, source_hash),
    }


def _write_immutable(path: Path, document: dict[str, Any]) -> str:
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise SystemExit(f"refusing to overwrite immutable artifact: {_rel(path)}")
    if not path.exists():
        path.write_text(payload, encoding="utf-8")
    digest = ca.sha256_file(path)
    sidecar = path.with_suffix(".json.sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"refusing to overwrite immutable sidecar: {_rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8")
    return digest


def register() -> dict[str, Any]:
    if MANIFEST.exists() or SIDECAR.exists():
        raise SystemExit("v16 domain/boundary contract already exists; refuse overwrite")
    if EVIDENCE.exists() or EVIDENCE_SIDECAR.exists():
        raise SystemExit("v16 domain/boundary evidence already exists; refuse overwrite")
    audit = _load(AUDIT)
    work_f = _load(WORK_F_MANIFEST)
    baseline = _load(BASELINE_MANIFEST)
    if audit.get("status") != "registered_solver_free_audit":
        raise SystemExit("the v16 contract audit is not in the expected solver-free state")
    if audit["candidate_binding"]["candidate_sha256"] != V16_CANDIDATE_SHA:
        raise SystemExit("the v16 audit candidate identity is unexpected")
    if _sha256(CANDIDATE) != V16_CANDIDATE_SHA:
        raise SystemExit("the v16 candidate STL changed")
    baseline_record = _baseline_record()
    if not baseline_record["qualified"]:
        raise SystemExit("the Work F V1 baseline is not profile-qualified")
    extended = _ensure_extended_inputs()
    common_boundary = {
        "inlet": "patch / U fixedValue freestream / p zeroGradient",
        "outlet": "patch / U zeroGradient / p fixedValue",
        "sideMin": "symmetryPlane",
        "sideMax": "symmetryPlane",
        "top": "symmetryPlane",
        "bottom": "wall / U noSlip / p zeroGradient",
        "design_candidate": "wall / U noSlip / p zeroGradient",
    }
    document = {
        "kind": "stage_v_v16_domain_boundary_contract_manifest",
        "schema_version": 1,
        "immutable": True,
        "status": "registered_not_run",
        "registered_before_computation": True,
        "evidence_class": "contract",
        "question": "Does the v16 candidate's Stage V response remain within the registered numerical band under each single domain/boundary factor?",
        "parent_contract_audit": _artifact(AUDIT),
        "baseline_manifest": _artifact(BASELINE_MANIFEST),
        "work_f_manifest": _artifact(WORK_F_MANIFEST),
        "candidate": {
            "label": baseline["candidate"]["label"],
            "stl": _artifact(CANDIDATE, V16_CANDIDATE_SHA),
            "same_candidate_as_stage_s": True,
        },
        "base_spec": {
            "raw": _artifact(BASE_SPEC),
            "canonical_sha256": problem_spec_sha256(load_problem_spec(BASE_SPEC)),
        },
        "baseline": baseline_record,
        "common_conditions": {
            "voxel_size_m": V1_VOXEL_M,
            "flow_case_id": "matched_re_laminar",
            "operating_point": {"velocity_mps": 1.0, "density": 1.0, "viscosity": 0.01, "turbulence_model": "laminar"},
            "force_patch": "design_candidate",
            "force_reference": {"area_m2": 0.64, "length_m": 0.8, "moment_center_m": [0.25, 0.0, 0.0]},
            "qualification_profile": "stage_v_qualification_v1",
            "openfoam_image": OPENFOAM_IMAGE,
            "openfoam_image_id": OPENFOAM_IMAGE_ID,
            "boundary_contract": common_boundary,
            "one_factor_at_a_time": True,
        },
        "treatments": [
            {
                "name": "far_field_domain_extension_0p8",
                "factor": "far-field domain size",
                "change": "extend inlet, outlet, sideMin, sideMax, and top by 0.8 m; bottom remains at z=-0.6 m",
                "far_field_faces": list(FAR_FIELD_FACES),
                "ground_face": GROUND_FACE,
                "boundary_contract": common_boundary,
                "extended_spec": extended,
                "case_dir": _rel(EXT_CASE),
            },
            {
                "name": "top_pressure_outlet",
                "factor": "far-field boundary treatment",
                "change": "replace only top symmetryPlane by patch with U zeroGradient and p fixedValue uniform 0 on the unchanged V1 domain",
                "boundary_contract": {**common_boundary, "top": "patch / U zeroGradient / p fixedValue uniform 0"},
                "case_dir": _rel(TOP_CASE),
            },
        ],
        "metric": {
            "downforce_absolute": 0.005,
            "drag_relative": 0.02,
            "comparison": "each treatment against the same v16 Work F V1 baseline",
            "source": "stage_v_qualification_v1 grid convergence bounds",
        },
        "budget": {"max_new_runs": 2, "mesh_levels": ["V1"], "v2_runs": 0, "v3_runs": 0},
        "stop_conditions": [
            "any pinned hash mismatch or candidate identity mismatch",
            "failed stage_v_clearance_v1 or stage_v_qualification_v1 mesh gate",
            "failed solver convergence or force stationarity",
            "either factor moves downforce or relative Cd beyond its registered bound; keep S2 blocked",
            "no new factor or boundary change may be added after a treatment result",
            "a passing factor screen does not establish grid-independent downforce or authorize S2/shape update",
        ],
        "claims_not_supported": [
            "grid-independent or absolute Stage V downforce",
            "reduced-basis FD qualification or shape update",
            "full-vehicle or high-Re FSAE qualification",
        ],
        "artifacts": {
            _rel(AUDIT): _artifact(AUDIT),
            _rel(BASELINE_MANIFEST): _artifact(BASELINE_MANIFEST),
            _rel(WORK_F_MANIFEST): _artifact(WORK_F_MANIFEST),
            _rel(BASELINE_SOLVER_EVIDENCE): _artifact(BASELINE_SOLVER_EVIDENCE),
            _rel(BASELINE_CASE / "stage_v_qualification.json"): _artifact(BASELINE_CASE / "stage_v_qualification.json"),
            _rel(BASELINE_CASE / "constant/triSurface/design_candidate.stl"): _artifact(BASELINE_CASE / "constant/triSurface/design_candidate.stl", V16_CANDIDATE_SHA),
            _rel(BASE_SPEC): _artifact(BASE_SPEC),
            _rel(DOMAIN_STL): _artifact(DOMAIN_STL),
            _rel(EXT_SPEC): _artifact(EXT_SPEC),
            _rel(EXT_DOMAIN_STL): _artifact(EXT_DOMAIN_STL),
            _rel(Path(__file__)): _artifact(Path(__file__)),
        },
        "execution": {
            "solver_started": False,
            "mesh_generation_started": False,
            "optimization_campaign_started": False,
            "new_run_count": 0,
        },
    }
    digest = _write_immutable(MANIFEST, document)
    print(json.dumps({"manifest": _rel(MANIFEST), "sha256": digest, "status": document["status"]}, ensure_ascii=False))
    return document


def _verify(manifest: dict[str, Any]) -> None:
    if manifest.get("status") != "registered_not_run":
        raise SystemExit("v16 contract is not in registered_not_run state")
    for key, ref in manifest["artifacts"].items():
        path = ROOT / ref["path"]
        if _sha256(_require(path)) != ref["sha256"]:
            raise SystemExit(f"registered artifact changed: {key}")
    if _sha256(MANIFEST) != SIDECAR.read_text(encoding="utf-8").strip():
        raise SystemExit("v16 contract sidecar mismatch")


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


def _baseline_location() -> tuple[float, float, float]:
    text = (BASELINE_CASE / "system/snappyHexMeshDict").read_text(encoding="utf-8")
    match = re.search(r"locationInMesh\s*\(\s*([^\)]+)\);", text)
    if match is None:
        raise SystemExit("baseline locationInMesh is missing")
    values = tuple(float(value) for value in match.group(1).split())
    if len(values) != 3:
        raise SystemExit("baseline locationInMesh must contain three coordinates")
    return values


def _patch_location_in_mesh(case_dir: Path) -> None:
    path = case_dir / "system/snappyHexMeshDict"
    text = path.read_text(encoding="utf-8")
    point = " ".join(f"{value:g}" for value in _baseline_location())
    updated, count = re.subn(r"locationInMesh\s*\([^\)]+\);", f"locationInMesh ({point});", text, count=1)
    if count != 1:
        raise SystemExit(f"could not patch locationInMesh in {_rel(path)}")
    path.write_text(updated, encoding="utf-8", newline="\n")


def _clean_case_outputs(case_dir: Path) -> None:
    """Remove every prior solver/post-processing artifact before a copied run.

    OpenFOAM renames a function-object output to ``coefficient_0.dat`` when a
    stale ``coefficient.dat`` is present.  The qualification reader intentionally
    reads the canonical ``coefficient.dat`` name, so preserving the copied
    ``postProcessing`` directory could silently qualify the baseline history
    instead of the treatment history.  A copied case must therefore start with
    no post-processing directory at all; the solver recreates it during the run.
    """
    if not case_dir.exists():
        return
    for child in list(case_dir.iterdir()):
        if child.is_dir() and child.name == "postProcessing":
            shutil.rmtree(child)
        elif child.is_dir() and child.name not in {"0", "constant", "system"}:
            shutil.rmtree(child)
        elif child.is_file() and child.name.startswith(("log.", "openfoam_run", "stage_v_", "top_outlet_edit")):
            child.unlink()


def _run_domain_extension(manifest: dict[str, Any], timeout: int) -> dict[str, Any]:
    treatment = next(item for item in manifest["treatments"] if item["name"] == "far_field_domain_extension_0p8")
    case_dir = ROOT / treatment["case_dir"]
    qualification_path = case_dir / "stage_v_qualification.json"
    if qualification_path.is_file() and _load(qualification_path).get("qualified"):
        return {"case_dir": treatment["case_dir"], **_responses(_load(qualification_path))}
    spec = load_problem_spec(EXT_SPEC)
    config = problem_spec_to_project_config(spec, candidate_stl=CANDIDATE, voxel_size_m=V1_VOXEL_M)
    mesh_log = case_dir / "log.checkMesh"
    solve_log = case_dir / "log.simpleFoam"
    if not mesh_log.exists():
        preflight = evaluate_stage_v_domain_preflight(spec, CANDIDATE, V1_VOXEL_M)
        if not preflight.qualified:
            raise SystemExit(f"v16 extended-domain preflight failed: {preflight.reasons}")
        write_stage_v_domain_preflight_report(case_dir, preflight)
        generate_openfoam_case(config, pq2._declared_domain_bundle(config), case_dir)
        _patch_location_in_mesh(case_dir)
        (case_dir / "location_in_mesh_patch.json").write_text(
            json.dumps({"source_case": _rel(BASELINE_CASE), "location_in_mesh": list(_baseline_location())}, indent=2) + "\n",
            encoding="utf-8",
        )
        (case_dir / "Allrun").write_text(MESH_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        run = run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=OPENFOAM_IMAGE)
        if getattr(run, "returncode", None) != 0:
            raise SystemExit("v16 extended-domain mesh run failed")
    check_mesh = evaluate_check_mesh(mesh_log.read_text(encoding="utf-8", errors="ignore"), STAGE_V_QUALIFICATION_PROFILE_V1)
    _write_stagev_level_preflight(case_dir, "stage_s_v16", "V1", V1_VOXEL_M, check_mesh, False, str(STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"]))
    if not check_mesh["qualified"]:
        raise SystemExit(f"v16 extended-domain checkMesh failed: {check_mesh['reasons']}")
    if not solve_log.exists():
        (case_dir / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        run = run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=OPENFOAM_IMAGE)
        if getattr(run, "returncode", None) != 0:
            raise SystemExit("v16 extended-domain solve run failed")
    write_stage_v_qualification(case_dir, STAGE_V_QUALIFICATION_PROFILE_V1)
    return {"case_dir": treatment["case_dir"], **_responses(_load(qualification_path))}


def _top_block(text: str) -> tuple[int, int]:
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if line.strip() != "top":
            continue
        index = start + 1
        while index < len(lines) and lines[index].strip() != "{":
            index += 1
        if index >= len(lines):
            break
        depth = 0
        while index < len(lines):
            depth += lines[index].count("{") - lines[index].count("}")
            if depth == 0 and index > start:
                return start, index
            index += 1
    raise SystemExit("top patch block is missing")


def _rewrite_top_boundary(case_dir: Path) -> None:
    path = case_dir / "constant/polyMesh/boundary"
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    start, end = _top_block(original)
    block = lines[start : end + 1]
    rewritten = []
    for line in block:
        if line.strip().startswith("type") and "symmetryPlane" in line:
            rewritten.append(line.replace("symmetryPlane", "patch"))
        elif line.strip().startswith("inGroups") and "symmetryPlane" in line:
            continue
        else:
            rewritten.append(line)
    if rewritten == block:
        raise SystemExit("top boundary treatment did not change the symmetry patch")
    path.write_text("\n".join(lines[:start] + rewritten + lines[end + 1 :]) + "\n", encoding="utf-8", newline="\n")


def _replace_top_field(path: Path, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = r"top\s*\{\s*type\s+symmetryPlane\s*;\s*\}"
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"top field treatment did not apply to {_rel(path)}")
    path.write_text(updated, encoding="utf-8", newline="\n")


def _run_top_outlet(manifest: dict[str, Any], timeout: int) -> dict[str, Any]:
    treatment = next(item for item in manifest["treatments"] if item["name"] == "top_pressure_outlet")
    case_dir = ROOT / treatment["case_dir"]
    qualification_path = case_dir / "stage_v_qualification.json"
    if qualification_path.is_file() and _load(qualification_path).get("qualified"):
        return {"case_dir": treatment["case_dir"], **_responses(_load(qualification_path))}
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASELINE_CASE, case_dir)
    _clean_case_outputs(case_dir)
    _rewrite_top_boundary(case_dir)
    _replace_top_field(case_dir / "0/U", "top { type zeroGradient; }")
    _replace_top_field(case_dir / "0/p", "top { type fixedValue; value uniform 0; }")
    (case_dir / "top_outlet_edit.json").write_text(json.dumps({"factor": "top_boundary", "changed": True}, indent=2) + "\n", encoding="utf-8")
    allrun = "#!/usr/bin/env bash\nset -euo pipefail\ncheckMesh -allGeometry -allTopology | tee log.checkMesh\nsimpleFoam | tee log.simpleFoam\npython3 postprocess_forces.py || python postprocess_forces.py || true\n"
    (case_dir / "Allrun").write_text(allrun, encoding="utf-8", newline="\n")
    run = run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=OPENFOAM_IMAGE)
    if getattr(run, "returncode", None) != 0:
        raise SystemExit("v16 top-pressure-outlet run failed")
    write_stage_v_qualification(case_dir, STAGE_V_QUALIFICATION_PROFILE_V1)
    return {"case_dir": treatment["case_dir"], **_responses(_load(qualification_path))}


def judge(manifest: dict[str, Any]) -> dict[str, Any]:
    if EVIDENCE.exists() or EVIDENCE_SIDECAR.exists():
        raise SystemExit("v16 domain/boundary evidence already exists; refuse overwrite")
    _verify(manifest)
    baseline = manifest["baseline"]
    bounds = manifest["metric"]
    rows: dict[str, Any] = {}
    for treatment in manifest["treatments"]:
        qualification_path = ROOT / treatment["case_dir"] / "stage_v_qualification.json"
        if not qualification_path.is_file():
            raise SystemExit(f"treatment is not run: {treatment['name']}")
        result = _responses(_load(qualification_path))
        delta_downforce = result["downforce"] - baseline["downforce"]
        relative_cd = (result["Cd"] - baseline["Cd"]) / baseline["Cd"]
        rows[treatment["name"]] = {
            "factor": treatment["factor"],
            "baseline": {"downforce": baseline["downforce"], "Cd": baseline["Cd"], "cells": baseline["cells"]},
            "treatment": result,
            "delta_downforce": delta_downforce,
            "relative_Cd_change": relative_cd,
            "downforce_beyond_bound": abs(delta_downforce) > bounds["downforce_absolute"],
            "drag_beyond_bound": abs(relative_cd) > bounds["drag_relative"],
            "stationarity_qualified": bool(result["qualified"]),
        }
    moving = [name for name, row in rows.items() if row["stationarity_qualified"] and row["downforce_beyond_bound"]]
    all_qualified = all(row["stationarity_qualified"] for row in rows.values())
    decision = (
        "v16 factor response remains outside the registered band; keep S2 blocked and register a revised contract"
        if moving or not all_qualified
        else "v16 factor response is within the registered band for this V1 screen; this does not establish grid independence"
    )
    evidence = {
        "kind": "stage_v_v16_domain_boundary_contract",
        "schema_version": 1,
        "manifest": {"path": _rel(MANIFEST), "sha256": _sha256(MANIFEST)},
        "candidate_sha256": V16_CANDIDATE_SHA,
        "baseline": baseline,
        "rows": rows,
        "registered_factors_moving_downforce": moving,
        "decision": decision,
        "summary": {"n_treatments": len(rows), "all_treatments_qualified": all_qualified, "any_downforce_moves_beyond_bound": bool(moving), "stage_s_s2_allowed": False},
        "claims_supported": ["two same-candidate V1 factor treatments were compared against the registered v16 Work F baseline"],
        "claims_not_supported": ["grid-independent or absolute Stage V downforce", "Stage S S2 qualification", "shape update or optimization authorization"],
    }
    digest = _write_immutable(EVIDENCE, evidence)
    print(json.dumps({"evidence": _rel(EVIDENCE), "sha256": digest, "decision": decision}, ensure_ascii=False))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="v16 Stage V domain/boundary factor contract")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run-domain-extension", action="store_true")
    parser.add_argument("--run-top-outlet", action="store_true")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
        return
    manifest = _load(MANIFEST)
    _verify(manifest)
    work_f = _load(WORK_F_MANIFEST)
    timeout = int(work_f["solver_budget"]["solver_timeout_seconds"])
    if args.run_domain_extension:
        print(json.dumps(_run_domain_extension(manifest, timeout), ensure_ascii=False))
    elif args.run_top_outlet:
        print(json.dumps(_run_top_outlet(manifest, timeout), ensure_ascii=False))
    elif args.judge:
        judge(manifest)
    else:
        parser.error("specify --register, --run-domain-extension, --run-top-outlet or --judge")


if __name__ == "__main__":
    main()
