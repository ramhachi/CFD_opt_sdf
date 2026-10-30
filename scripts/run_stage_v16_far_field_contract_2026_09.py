#!/usr/bin/env python3
"""Register and run a physically defined far-field boundary contract for v16.

The domain-only ladder is stopped at the +3.2 m box.  This contract keeps that
candidate, mesh, domain, operating point, and force normalization fixed and
changes only the five outer faces from the symmetry/patch mixture to a mixed
freestream formulation:

* mesh boundary type: ``patch``;
* ``U``: ``freestreamVelocity`` with the declared free-stream vector;
* ``p``: ``freestreamPressure`` with free-stream pressure zero and ``U U``.

The ground and candidate walls are unchanged.  The contract is executed only
after registration and never authorizes S2 or a shape update.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_stage_v16_domain_continuation_3p2_2026_09 as d32  # noqa: E402
from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1, evaluate_check_mesh, write_stage_v_qualification  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from stage_t_filtered_ramp import SOLVE_ONLY_ALLRUN  # noqa: E402


OUT_ROOT = ROOT / "work/stage_v_v16_far_field_contract_2026_09"
CASE_DIR = OUT_ROOT / "mixed_outer/V1"
MANIFEST = ROOT / "docs/evidence/stage_v_v16_far_field_contract_manifest_v2_2026_09.json"
RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_far_field_contract_run_manifest_v2_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_v16_far_field_contract_v2_2026_09.json"

BASE_CASE = d32.CASE_DIR
BASE_QUALIFICATION = BASE_CASE / "stage_v_qualification.json"
BASE_SPEC = d32.BASE_SPEC
CANDIDATE = d32.CANDIDATE
V16_CANDIDATE_SHA = d32.V16_CANDIDATE_SHA
V1_VOXEL_M = d32.V1_VOXEL_M
OPENFOAM_IMAGE = d32.OPENFOAM_IMAGE
OUTER_PATCHES = ("inlet", "outlet", "sideMin", "sideMax", "top")
FREESTREAM_VECTOR = (1.0, 0.0, 0.0)


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"required file is missing: {_rel(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(path: Path, expected: str | None = None) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"required artifact is missing: {_rel(path)}")
    observed = _sha256(path)
    if expected is not None and observed != expected:
        raise SystemExit(f"hash mismatch for {_rel(path)}: expected {expected}, observed {observed}")
    return {"path": _rel(path), "sha256": observed}


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


def _patch_block(text: str, patch: str) -> tuple[list[str], int, int]:
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if line.strip() != patch:
            continue
        index = start + 1
        while index < len(lines) and lines[index].strip() != "{":
            index += 1
        if index >= len(lines):
            break
        depth = 0
        for end in range(index, len(lines)):
            depth += lines[end].count("{") - lines[end].count("}")
            if depth == 0:
                return lines, start, end
    raise SystemExit(f"patch block is missing: {patch}")


def _rewrite_mesh_boundary(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for patch in OUTER_PATCHES:
        lines, start, end = _patch_block("\n".join(lines), patch)
        block = lines[start : end + 1]
        rewritten: list[str] = []
        for line in block:
            stripped = line.strip()
            if stripped.startswith("type") and "symmetryPlane" in line:
                rewritten.append(line.replace("symmetryPlane", "patch"))
            elif stripped.startswith("inGroups") and "symmetryPlane" in line:
                continue
            else:
                rewritten.append(line)
        lines[start : end + 1] = rewritten
    updated = "\n".join(lines) + "\n"
    for patch in OUTER_PATCHES:
        _, start, end = _patch_block(updated, patch)
        block = "\n".join(updated.splitlines()[start : end + 1])
        if re.search(r"(?m)^\s*type\s+patch\s*;", block) is None:
            raise SystemExit(f"outer mesh patch was not converted to patch: {patch}")
    path.write_text(updated, encoding="utf-8", newline="\n")


def _field_replacement(field: str, patch: str) -> str:
    indent = "    "
    if field == "U":
        return (
            f"{indent}{patch}\n{indent}{{\n"
            f"        type            freestreamVelocity;\n"
            f"        freestreamValue uniform (1 0 0);\n"
            f"        value           uniform (1 0 0);\n"
            f"{indent}}}"
        )
    if field == "p":
        return (
            f"{indent}{patch}\n{indent}{{\n"
            f"        type            freestreamPressure;\n"
            f"        freestreamValue uniform 0;\n"
            f"        U               U;\n"
            f"        value           uniform 0;\n"
            f"{indent}}}"
        )
    raise SystemExit(f"unsupported far-field field: {field}")


def _rewrite_field(path: Path, field: str) -> None:
    text = path.read_text(encoding="utf-8")
    for patch in OUTER_PATCHES:
        pattern = rf"(?ms)^[ \t]*{re.escape(patch)}[ \t]*\{{.*?\}}"
        text, count = re.subn(pattern, _field_replacement(field, patch), text, count=1)
        if count != 1:
            raise SystemExit(f"field patch was not rewritten: {_rel(path)}:{patch}")
    path.write_text(text, encoding="utf-8", newline="\n")


def _clean_case_outputs(case_dir: Path) -> None:
    for child in list(case_dir.iterdir()):
        if child.is_dir() and child.name not in {"0", "constant", "system"}:
            shutil.rmtree(child)
        elif child.is_file() and child.name.startswith(("log.", "openfoam_run", "stage_v_", "far_field")):
            child.unlink()


def _rewrite_case(case_dir: Path) -> None:
    _rewrite_mesh_boundary(case_dir / "constant/polyMesh/boundary")
    _rewrite_field(case_dir / "0/U", "U")
    _rewrite_field(case_dir / "0/p", "p")
    metadata = {
        "kind": "v16_far_field_boundary_edit",
        "outer_patches": list(OUTER_PATCHES),
        "mesh_type": "patch",
        "U": {"type": "freestreamVelocity", "freestreamValue": list(FREESTREAM_VECTOR)},
        "p": {"type": "freestreamPressure", "freestreamValue": 0.0, "U": "U"},
        "unchanged_walls": ["bottom", "design_candidate"],
        "source_case": _rel(BASE_CASE),
    }
    (case_dir / "far_field_boundary_edit.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def register() -> dict[str, Any]:
    if any(path.exists() for path in (MANIFEST, RUN_MANIFEST, EVIDENCE)):
        raise SystemExit("v16 far-field contract artifacts already exist; refuse overwrite")
    factor_manifest = _load(d32.FACTOR_MANIFEST)
    factor_evidence = _load(d32.FACTOR_EVIDENCE)
    continuation_evidence = _load(d32.EVIDENCE)
    if continuation_evidence.get("decision") != "v16 +1.6 m to +3.2 m transition remains outside the registered band; stop domain-only expansion and register a physically justified far-field contract while keeping S2 blocked":
        raise SystemExit("the +3.2 m evidence does not authorize the far-field contract")
    if factor_evidence.get("candidate_sha256") != V16_CANDIDATE_SHA or _sha256(CANDIDATE) != V16_CANDIDATE_SHA:
        raise SystemExit("the v16 candidate identity is not pinned")
    base_qualification = _load(BASE_QUALIFICATION)
    if not base_qualification.get("qualified"):
        raise SystemExit("the +3.2 m baseline is not profile-qualified")
    base_response = {"case_dir": _rel(BASE_CASE), **_responses(base_qualification)}
    artifacts = {
        _rel(d32.FACTOR_MANIFEST): _artifact(d32.FACTOR_MANIFEST),
        _rel(d32.FACTOR_EVIDENCE): _artifact(d32.FACTOR_EVIDENCE),
        _rel(d32.FACTOR_LINEAGE): _artifact(d32.FACTOR_LINEAGE),
        _rel(d32.RUN_MANIFEST): _artifact(d32.RUN_MANIFEST),
        _rel(d32.EVIDENCE): _artifact(d32.EVIDENCE),
        _rel(CANDIDATE): _artifact(CANDIDATE, V16_CANDIDATE_SHA),
        _rel(BASE_SPEC): _artifact(BASE_SPEC),
        _rel(BASE_QUALIFICATION): _artifact(BASE_QUALIFICATION),
        _rel(BASE_CASE / "constant/polyMesh/boundary"): _artifact(BASE_CASE / "constant/polyMesh/boundary"),
        _rel(BASE_CASE / "0/U"): _artifact(BASE_CASE / "0/U"),
        _rel(BASE_CASE / "0/p"): _artifact(BASE_CASE / "0/p"),
        _rel(Path(__file__)): _artifact(Path(__file__)),
    }
    run_document = {
        "kind": "stage_v_v16_far_field_contract_run_manifest",
        "schema_version": 1,
        "immutable": True,
        "registered_before_computation": True,
        "status": "registered_not_run",
        "evidence_class": "contract",
        "question": "At the largest registered v16 V1 domain, does a mixed freestreamVelocity/freestreamPressure outer boundary remove the response dependence on the symmetry/patch mixture without changing the candidate, mesh, or operating point?",
        "parents": {"factor_manifest": _artifact(d32.FACTOR_MANIFEST), "factor_evidence": _artifact(d32.FACTOR_EVIDENCE), "continuation_manifest": _artifact(d32.RUN_MANIFEST), "continuation_evidence": _artifact(d32.EVIDENCE), "lineage_audit": _artifact(d32.FACTOR_LINEAGE)},
        "candidate": {"stl": _artifact(CANDIDATE, V16_CANDIDATE_SHA), "same_candidate_as_stage_s": True},
        "baseline": base_response,
        "treatment": {
            "name": "mixed_freestream_outer",
            "factor": "far-field boundary formulation",
            "base_domain": "+3.2 m from the original v16 V1 box",
            "change": "convert inlet/outlet/sideMin/sideMax/top to patch; use freestreamVelocity for U and freestreamPressure for p",
            "outer_patches": list(OUTER_PATCHES),
            "boundary_contract": {patch: {"mesh": "patch", "U": "freestreamVelocity", "p": "freestreamPressure"} for patch in OUTER_PATCHES} | {"bottom": {"mesh": "wall", "U": "noSlip", "p": "zeroGradient"}, "design_candidate": {"mesh": "wall", "U": "noSlip", "p": "zeroGradient"}},
            "openfoam_reference": {"U": "freestreamVelocity", "p": "freestreamPressure", "freestream_value": [1.0, 0.0, 0.0], "pressure_value": 0.0},
            "case_dir": _rel(CASE_DIR),
        },
        "metric": {"downforce_absolute": 0.005, "drag_relative": 0.02, "comparison": "same +3.2 m domain baseline to mixed far-field treatment"},
        "budget": {"max_new_runs": 1, "mesh_levels": ["V1"], "v2_runs": 0, "v3_runs": 0},
        "artifacts": artifacts,
        "stop_conditions": ["any pinned hash or candidate mismatch", "boundary edit differs from the registered mixed contract", "failed solver convergence or force stationarity", "response change outside the bound keeps S2 blocked", "a passing boundary factor does not establish grid independence"],
        "claims_not_supported": ["grid-independent or absolute Stage V downforce", "reduced-basis FD qualification or shape update", "full-vehicle or high-Re FSAE qualification"],
        "execution": {"solver_started": False, "mesh_generation_started": False, "optimization_campaign_started": False, "new_run_count": 0},
    }
    run_digest = _write_immutable(RUN_MANIFEST, run_document)
    parent = {"kind": "stage_v_v16_far_field_contract_manifest", "schema_version": 1, "immutable": True, "registered_before_computation": True, "status": "registered_not_run", "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": run_digest}, "question": run_document["question"], "candidate": run_document["candidate"], "baseline": base_response, "treatment": run_document["treatment"], "metric": run_document["metric"], "budget": run_document["budget"], "claims_not_supported": run_document["claims_not_supported"]}
    parent_digest = _write_immutable(MANIFEST, parent)
    print(json.dumps({"run_manifest": _rel(RUN_MANIFEST), "run_manifest_sha256": run_digest, "manifest": _rel(MANIFEST), "manifest_sha256": parent_digest}, ensure_ascii=False))
    return run_document


def _verify(manifest: dict[str, Any]) -> None:
    if manifest.get("status") != "registered_not_run":
        raise SystemExit("v16 far-field contract is not registered_not_run")
    for key, ref in manifest["artifacts"].items():
        if _sha256(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"registered artifact changed: {key}")
    if _sha256(RUN_MANIFEST) != RUN_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("far-field run-manifest sidecar mismatch")


def _run(manifest: dict[str, Any], timeout: int) -> dict[str, Any]:
    _verify(manifest)
    qualification_path = CASE_DIR / "stage_v_qualification.json"
    if qualification_path.is_file() and _load(qualification_path).get("qualified"):
        return {"case_dir": _rel(CASE_DIR), **_responses(_load(qualification_path))}
    if CASE_DIR.exists():
        shutil.rmtree(CASE_DIR)
    CASE_DIR.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASE_CASE, CASE_DIR)
    _clean_case_outputs(CASE_DIR)
    _rewrite_case(CASE_DIR)
    (CASE_DIR / "Allrun").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ncheckMesh -allGeometry -allTopology | tee log.checkMesh\n" + SOLVE_ONLY_ALLRUN,
        encoding="utf-8",
        newline="\n",
    )
    result = run_openfoam_case(CASE_DIR, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=OPENFOAM_IMAGE)
    if getattr(result, "returncode", None) != 0:
        raise SystemExit("v16 far-field contract run failed")
    write_stage_v_qualification(CASE_DIR, STAGE_V_QUALIFICATION_PROFILE_V1)
    return {"case_dir": _rel(CASE_DIR), **_responses(_load(qualification_path))}


def judge() -> dict[str, Any]:
    if EVIDENCE.exists():
        raise SystemExit("v16 far-field evidence already exists; refuse overwrite")
    manifest = _load(RUN_MANIFEST)
    _verify(manifest)
    treatment = _responses(_load(CASE_DIR / "stage_v_qualification.json"))
    baseline = manifest["baseline"]
    delta_downforce = treatment["downforce"] - baseline["downforce"]
    relative_cd = (treatment["Cd"] - baseline["Cd"]) / baseline["Cd"]
    metric = manifest["metric"]
    within = treatment["qualified"] and abs(delta_downforce) <= metric["downforce_absolute"] and abs(relative_cd) <= metric["drag_relative"]
    decision = (
        "mixed far-field response is within the registered band on the +3.2 m v16 box; keep Stage S blocked pending a separate absolute/grid audit"
        if within
        else "mixed far-field response remains outside the registered band; keep S2 blocked and perform a case-construction/boundary audit before any further solver run"
    )
    evidence = {"kind": "stage_v_v16_far_field_contract", "schema_version": 1, "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": _sha256(RUN_MANIFEST)}, "candidate_sha256": V16_CANDIDATE_SHA, "baseline": baseline, "treatment": treatment, "delta": {"downforce": delta_downforce, "relative_Cd_change": relative_cd, "downforce_beyond_bound": abs(delta_downforce) > metric["downforce_absolute"], "drag_beyond_bound": abs(relative_cd) > metric["drag_relative"]}, "decision": decision, "summary": {"qualified": treatment["qualified"], "within_registered_band": within, "stage_s_s2_allowed": False}, "claims_supported": ["one same-candidate v16 +3.2 m far-field boundary treatment was compared with its symmetry/patch baseline"], "claims_not_supported": ["grid-independent or absolute Stage V downforce", "Stage S S2 qualification", "shape update or optimization authorization"]}
    digest = _write_immutable(EVIDENCE, evidence)
    print(json.dumps({"evidence": _rel(EVIDENCE), "sha256": digest, "decision": decision}, ensure_ascii=False))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="same-candidate v16 mixed far-field boundary contract")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--judge", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.run:
        manifest = _load(RUN_MANIFEST)
        work_f = _load(d32.base.v16.WORK_F_MANIFEST)
        print(json.dumps(_run(manifest, int(work_f["solver_budget"]["solver_timeout_seconds"])), ensure_ascii=False))
    elif args.judge:
        judge()
    else:
        parser.error("specify --register, --run or --judge")


if __name__ == "__main__":
    main()
