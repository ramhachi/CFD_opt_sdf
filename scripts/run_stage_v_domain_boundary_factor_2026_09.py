"""PQ2 Stage V domain/boundary factor campaign (V2 only, two treatments).

``--register`` fixes the two treatment definitions that the registered PQ2
manifest left to be "chosen and recorded before the run":

- far-field domain extension by one body length (0.8 m) on the five far-field
  faces (inlet, outlet, sideMin, sideMax, top); the bottom ground wall stays at
  z=-0.6 so the ground clearance is not confounded;
- pressure-outlet on the top face (U zeroGradient, p fixedValue 0) on the
  unchanged baseline domain and mesh.

``--run`` executes the treatments at the registered V2 resolution (0.025 m)
against the already-qualified fixed-domain V2 baseline, and ``--judge`` writes
the comparison evidence against the registered bounds. No V3 run and no
treatment definition change after a result.
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

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import (  # noqa: E402
    STAGE_V_QUALIFICATION_PROFILE_V1,
    evaluate_check_mesh,
    qualify_stage_v_case,
    write_stage_v_qualification,
)
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.sdf import build_fields  # noqa: E402
from cfd_sdf.stage_v_domain_preflight import (  # noqa: E402
    evaluate_stage_v_domain_preflight,
    write_stage_v_domain_preflight_report,
)
from stage_t_filtered_ramp import (  # noqa: E402
    MESH_ONLY_ALLRUN,
    SOLVE_ONLY_ALLRUN,
    _write_stagev_level_preflight,
)

TOP_OUTLET_ALLRUN = (
    "#!/usr/bin/env bash\n"
    "set -euo pipefail\n"
    "checkMesh -allGeometry -allTopology | tee log.checkMesh\n"
    "simpleFoam | tee log.simpleFoam\n"
    "python3 postprocess_forces.py || python postprocess_forces.py || true\n"
)

PQ2_MANIFEST = ROOT / "docs/evidence/stage_v_domain_boundary_factor_manifest_2026_09.json"
FIXED_DOMAIN_EVIDENCE = ROOT / "docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json"
BASELINE_CASE = ROOT / "work/stage_v_fixed_domain_2026_09/opt_q100_b0_step0_try0_block/V2"
CANDIDATE = ROOT / "work/filtered_ramp/wmin_0.2/export/opt_q100_b0_step0_try0_block/iso_surface.stl"
SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
ROOT_OUT = ROOT / "work/stage_v_domain_boundary_factor_2026_09"
EXT_SPEC = ROOT_OUT / "specs/project_matched_re_laminar_domain_extended_v1.yaml"
T1_CASE = ROOT_OUT / "far_field_domain_extension/V2"
T2_CASE = ROOT_OUT / "top_pressure_outlet/V2"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_domain_boundary_factor_run_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_domain_boundary_factor_2026_09.json"
V2_VOXEL_M = 0.025
EXTENSION_M = 0.8
FAR_FIELD_FACES = ("inlet", "outlet", "sideMin", "sideMax", "top")
GROUND_FACE = "bottom"
TOP_TREATMENT = {"U": "zeroGradient", "p": "fixedValue uniform 0"}
CID = "opt_q100_b0_step0_try0_block"
LEVEL = "V2"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _baseline_record() -> dict:
    qualification = ca.load_json(BASELINE_CASE / "stage_v_qualification.json")
    responses = qualification["force_stationarity"]["responses"]
    return {
        "case_dir": str(BASELINE_CASE.relative_to(ROOT)),
        "qualification_path": str((BASELINE_CASE / "stage_v_qualification.json").relative_to(ROOT)),
        "qualification_sha256": _sha256(BASELINE_CASE / "stage_v_qualification.json"),
        "qualified": bool(qualification.get("qualified")),
        "cells": int(qualification["check_mesh"]["total_cells"]),
        "iterations": qualification["solver"].get("iteration_count"),
        "Cd": float(responses["Cd"]["mean"]),
        "downforce": float(responses["downforce"]["mean"]),
    }


def _extended_spec() -> dict:
    raw = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    extended = copy.deepcopy(raw)
    bounds = raw["grid"]["domain_bounds_m"]
    extended["problem_id"] = f"{raw['problem_id']}_domain_extended_v1"
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


def _ensure_extended_spec() -> dict:
    extended = _extended_spec()
    EXT_SPEC.parent.mkdir(parents=True, exist_ok=True)
    if EXT_SPEC.exists():
        existing = yaml.safe_load(EXT_SPEC.read_text(encoding="utf-8"))
        if existing != extended:
            raise SystemExit("the existing extended-domain spec does not match the deterministic construction")
    else:
        EXT_SPEC.write_text(
            yaml.safe_dump(extended, sort_keys=False, default_flow_style=False), encoding="utf-8"
        )
    raw = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    diff = sorted(key for key in set(raw) | set(extended) if raw.get(key) != extended.get(key))
    if diff != ["grid", "problem_id"]:
        raise SystemExit(f"the extended spec differs beyond the domain bounds: {diff}")
    spec = load_problem_spec(EXT_SPEC)
    return {
        "path": str(EXT_SPEC.relative_to(ROOT)),
        "sha256": _sha256(EXT_SPEC),
        "diff_keys": diff,
        "lower_m": list(spec.grid.domain_bounds_m.lower),
        "upper_m": list(spec.grid.domain_bounds_m.upper),
    }


def register() -> dict:
    if RUN_MANIFEST.exists():
        raise SystemExit("PQ2 run manifest already exists; refuse overwrite")
    pq2 = ca.load_json(PQ2_MANIFEST)
    fixed = ca.load_json(FIXED_DOMAIN_EVIDENCE)
    if pq2.get("status") != "registered_not_run":
        raise SystemExit("the registered PQ2 manifest is not in the registered_not_run state")
    if _sha256(CANDIDATE) != fixed["fixed_conditions"]["candidate_stl_sha256"]:
        raise SystemExit("the candidate STL does not match the fixed-domain study")
    baseline = _baseline_record()
    if not baseline["qualified"]:
        raise SystemExit("the fixed-domain V2 baseline is not qualified")
    extended = _ensure_extended_spec()
    manifest = {
        "kind": "stage_v_domain_boundary_factor_run_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "question": pq2["question"],
        "pq2_manifest": {"path": str(PQ2_MANIFEST.relative_to(ROOT)), "sha256": _sha256(PQ2_MANIFEST)},
        "fixed_domain_evidence": {
            "path": str(FIXED_DOMAIN_EVIDENCE.relative_to(ROOT)),
            "sha256": _sha256(FIXED_DOMAIN_EVIDENCE),
        },
        "candidate": {
            "case_id": CID,
            "stl": {"path": str(CANDIDATE.relative_to(ROOT)), "sha256": _sha256(CANDIDATE)},
        },
        "base_spec": {"path": str(SPEC.relative_to(ROOT)), "sha256": _sha256(SPEC)},
        "baseline": baseline,
        "treatments": [
            {
                "name": "far_field_domain_extension",
                "factor": "far-field domain size",
                "baseline": "declared fixed domain lower=(-1.0,-0.8,-0.6), upper=(2.0,0.8,0.6)",
                "treatment": (
                    "extend inlet/outlet/sideMin/sideMax/top by 0.8 m; the bottom ground wall "
                    "stays at z=-0.6 so the ground clearance is not confounded"
                ),
                "far_field_faces": list(FAR_FIELD_FACES),
                "ground_face": GROUND_FACE,
                "extended_spec": extended,
                "voxel_size_m": V2_VOXEL_M,
                "case_dir": str(T1_CASE.relative_to(ROOT)),
            },
            {
                "name": "top_pressure_outlet",
                "factor": "far-field boundary treatment",
                "baseline": "top face symmetryPlane on the fixed-domain family",
                "treatment": "pressure outlet on the top face: U zeroGradient, p fixedValue uniform 0",
                "top_patch": TOP_TREATMENT,
                "domain": "unchanged baseline domain and V2 mesh",
                "case_dir": str(T2_CASE.relative_to(ROOT)),
            },
        ],
        "metric": pq2["metric"],
        "decision": pq2["decision"],
        "stop_conditions": pq2["stop_conditions"],
        "budget": {"max_new_runs": 2, "v3_runs": 0, "note": "V2 level only"},
        "fixed_conditions": pq2["fixed_conditions"],
        "claims_not_supported": [
            "this campaign is V2-only and does not produce a grid-independent downforce reference",
        ],
    }
    RUN_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(RUN_MANIFEST.relative_to(ROOT)), "sha256": _sha256(RUN_MANIFEST)}, indent=2))
    return manifest


def _verify(manifest: dict) -> None:
    for key in ("pq2_manifest", "fixed_domain_evidence"):
        record = manifest[key]
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"registered input changed: {key}")
    if _sha256(ROOT / manifest["candidate"]["stl"]["path"]) != manifest["candidate"]["stl"]["sha256"]:
        raise SystemExit("the candidate STL changed")
    if _sha256(ROOT / manifest["base_spec"]["path"]) != manifest["base_spec"]["sha256"]:
        raise SystemExit("the base spec changed")
    if _sha256(BASELINE_CASE / "stage_v_qualification.json") != manifest["baseline"]["qualification_sha256"]:
        raise SystemExit("the baseline V2 qualification changed")


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


def _run_domain_extension(manifest: dict, timeout: int, image: str) -> dict:
    treatment = manifest["treatments"][0]
    case_dir = ROOT / treatment["case_dir"]
    qualification_path = case_dir / "stage_v_qualification.json"
    mesh_log = case_dir / "log.checkMesh"
    solve_log = case_dir / "log.simpleFoam"
    if qualification_path.exists() and ca.load_json(qualification_path).get("qualified"):
        return {"case_dir": treatment["case_dir"], **_responses(ca.load_json(qualification_path))}
    if solve_log.exists():
        # a stale unqualified solve log blocks a clean retry
        solve_log.unlink()
        for child in list(case_dir.iterdir()):
            if child.is_dir() and child.name not in {"0", "constant", "system"}:
                shutil.rmtree(child)
    spec = load_problem_spec(EXT_SPEC)
    config = problem_spec_to_project_config(spec, candidate_stl=CANDIDATE, voxel_size_m=V2_VOXEL_M)
    if not solve_log.exists():
        if not mesh_log.exists():
            preflight = evaluate_stage_v_domain_preflight(spec, CANDIDATE, V2_VOXEL_M)
            if not preflight.qualified:
                raise SystemExit(f"extended-domain preflight failed: {preflight.reasons}")
            write_stage_v_domain_preflight_report(case_dir, preflight)
            generate_openfoam_case(config, build_fields(config), case_dir)
            (case_dir / "Allrun").write_text(MESH_ONLY_ALLRUN, encoding="utf-8", newline="\n")
            run = run_openfoam_case(
                case_dir, backend="docker", dry_run=False, timeout_seconds=7200, docker_image=image
            )
            if getattr(run, "returncode", None) != 0:
                raise SystemExit("extended-domain mesh run failed")
        check_mesh = evaluate_check_mesh(
            mesh_log.read_text(encoding="utf-8", errors="ignore"), STAGE_V_QUALIFICATION_PROFILE_V1
        )
        _write_stagev_level_preflight(
            case_dir, CID, LEVEL, V2_VOXEL_M, check_mesh, False,
            str(STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"]),
        )
        if not check_mesh["qualified"]:
            raise SystemExit(f"extended-domain checkMesh failed: {check_mesh['reasons']}")
        (case_dir / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        run = run_openfoam_case(
            case_dir, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=image
        )
        if getattr(run, "returncode", None) != 0:
            raise SystemExit("extended-domain solve run failed")
    write_stage_v_qualification(case_dir, STAGE_V_QUALIFICATION_PROFILE_V1)
    qualification = ca.load_json(qualification_path)
    return {"case_dir": treatment["case_dir"], **_responses(qualification)}


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
        break
    raise SystemExit("the boundary file has no top patch block")


def _rewrite_top_patch_type(case_dir: Path) -> dict:
    path = case_dir / "constant" / "polyMesh" / "boundary"
    original = path.read_text(encoding="utf-8")
    start, end = _top_block(original)
    lines = original.splitlines()
    block = lines[start : end + 1]
    rewritten: list[str] = []
    for line in block:
        if "symmetryPlane" in line and line.strip().startswith("type"):
            rewritten.append(line.replace("symmetryPlane", "patch"))
        elif "symmetryPlane" in line and line.strip().startswith("inGroups"):
            continue
        else:
            rewritten.append(line)
    if block == rewritten:
        raise SystemExit("the top patch type was not changed")
    treated = "\n".join(lines[:start] + rewritten + lines[end + 1 :]) + "\n"
    path.write_text(treated, encoding="utf-8", newline="\n")
    return {"removed_lines": [line for line in block if line not in rewritten], "added_lines": [line for line in rewritten if line not in block]}


def _run_top_outlet(manifest: dict, timeout: int, image: str) -> dict:
    treatment = manifest["treatments"][1]
    case_dir = ROOT / treatment["case_dir"]
    qualification_path = case_dir / "stage_v_qualification.json"
    if qualification_path.exists() and ca.load_json(qualification_path).get("qualified"):
        return {"case_dir": treatment["case_dir"], **_responses(ca.load_json(qualification_path))}
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASELINE_CASE, case_dir)
    for child in list(case_dir.iterdir()):
        if child.is_dir() and child.name not in {"0", "constant", "system"}:
            shutil.rmtree(child)
        elif child.is_file() and child.name.startswith(("log.", "openfoam_run", "stage_v")):
            child.unlink()
    boundary_edit = _rewrite_top_patch_type(case_dir)
    for field, expected in (("U", "zeroGradient"), ("p", "fixedValue")):
        path = case_dir / "0" / field
        text = path.read_text(encoding="utf-8")
        if field == "U":
            treated_field = text.replace(
                "top { type symmetryPlane; }", "top { type zeroGradient; }"
            )
        else:
            treated_field = text.replace(
                "top { type symmetryPlane; }",
                "top { type fixedValue; value uniform 0; }",
            )
        if treated_field == text or expected not in treated_field:
            raise SystemExit(f"the top {field} treatment did not apply cleanly")
        path.write_text(treated_field, encoding="utf-8", newline="\n")
    (case_dir / "Allrun").write_text(TOP_OUTLET_ALLRUN, encoding="utf-8", newline="\n")
    run = run_openfoam_case(
        case_dir, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=image
    )
    if getattr(run, "returncode", None) != 0:
        raise SystemExit("top-outlet solve run failed")
    (case_dir / "top_outlet_edit.json").write_text(
        json.dumps(boundary_edit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_stage_v_qualification(case_dir, STAGE_V_QUALIFICATION_PROFILE_V1)
    qualification = ca.load_json(case_dir / "stage_v_qualification.json")
    return {"case_dir": treatment["case_dir"], **_responses(qualification)}


def judge() -> dict:
    if EVIDENCE.exists():
        raise SystemExit("PQ2 evidence already exists; refuse overwrite")
    manifest = ca.load_json(RUN_MANIFEST)
    _verify(manifest)
    baseline = manifest["baseline"]
    rows = {}
    treatment_results = []
    for treatment in manifest["treatments"]:
        qualification_path = ROOT / treatment["case_dir"] / "stage_v_qualification.json"
        if not qualification_path.is_file():
            raise SystemExit(f"treatment is not run yet: {treatment['name']}")
        treatment_results.append(_responses(ca.load_json(qualification_path)))
    t1, t2 = treatment_results
    bounds = manifest["metric"]["bounds"]
    for treatment in manifest["treatments"]:
        result = t1 if treatment["name"] == "far_field_domain_extension" else t2
        delta_downforce = result["downforce"] - baseline["downforce"]
        relative_cd = (result["Cd"] - baseline["Cd"]) / baseline["Cd"]
        rows[treatment["name"]] = {
            "factor": treatment["factor"],
            "baseline": {"downforce": baseline["downforce"], "Cd": baseline["Cd"], "cells": baseline["cells"]},
            "treatment": result,
            "delta_downforce": delta_downforce,
            "relative_Cd_change": relative_cd,
            "downforce_beyond_bound": bool(abs(delta_downforce) > bounds["downforce_absolute"]),
            "drag_beyond_bound": bool(abs(relative_cd) > bounds["drag_relative"]),
            "stationarity_qualified": bool(result["qualified"]),
        }
    registered_factors = [
        name for name, row in rows.items() if row["downforce_beyond_bound"] and row["stationarity_qualified"]
    ]
    decision = (
        "register the moving factor(s) and rerun the family: " + ", ".join(registered_factors)
        if registered_factors
        else "no factor moves the V2 downforce beyond the registered bound; "
        "accept the residual as a measured candidate-specific band and register no further factor"
    )
    evidence = {
        "kind": "stage_v_domain_boundary_factor",
        "schema_version": 1,
        "run_manifest": {"path": str(RUN_MANIFEST.relative_to(ROOT)), "sha256": _sha256(RUN_MANIFEST)},
        "baseline": baseline,
        "rows": rows,
        "registered_factors_moving_downforce": registered_factors,
        "decision": decision,
        "summary": {
            "n_treatments": 2,
            "all_treatments_qualified": bool(all(row["stationarity_qualified"] for row in rows.values())),
            "any_downforce_moves_beyond_bound": bool(registered_factors),
            "v3_runs": 0,
        },
        "claims_supported": [
            "two V2 treatments were run against the qualified fixed-domain V2 baseline and compared to the registered bounds",
        ],
        "claims_not_supported": [
            "no grid-independent downforce reference and no V3 run",
            "the decision is a bounded factor registration, not a qualification of the Stage V reference",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    print(decision)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="PQ2 Stage V domain/boundary factor campaign")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run-domain-extension", action="store_true")
    parser.add_argument("--run-top-outlet", action="store_true")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    work_f = ca.load_json(ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json")
    timeout = int(work_f["solver_budget"]["solver_timeout_seconds"])
    image = work_f["openfoam_image"]
    if args.register:
        register()
    elif args.run_domain_extension:
        manifest = ca.load_json(RUN_MANIFEST)
        _verify(manifest)
        print(json.dumps(_run_domain_extension(manifest, timeout, image), indent=2))
    elif args.run_top_outlet:
        manifest = ca.load_json(RUN_MANIFEST)
        _verify(manifest)
        print(json.dumps(_run_top_outlet(manifest, timeout, image), indent=2))
    elif args.judge:
        judge()
    else:
        parser.error("specify --register, --run-domain-extension, --run-top-outlet or --judge")


if __name__ == "__main__":
    main()
