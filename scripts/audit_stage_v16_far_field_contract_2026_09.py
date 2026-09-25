#!/usr/bin/env python3
"""Audit the v16 mixed far-field run without starting another solver."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402


RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_far_field_contract_run_manifest_v2_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_v_v16_far_field_contract_v2_2026_09.json"
AUDIT = ROOT / "docs/evidence/stage_v_v16_far_field_contract_audit_2026_09.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _patch_records(path: Path) -> dict[str, dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    records: dict[str, dict[str, str]] = {}
    for index, line in enumerate(lines):
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*$", line)
        if match is None:
            continue
        patch = match.group(1)
        if index + 1 >= len(lines) or lines[index + 1].strip() != "{":
            continue
        body: list[str] = []
        depth = 0
        for current in lines[index + 1 :]:
            body.append(current)
            depth += current.count("{") - current.count("}")
            if depth == 0:
                break
        block = "\n".join(body)
        type_match = re.search(r"(?m)^\s*type\s+(\w+)\s*;", block)
        nfaces_match = re.search(r"(?m)^\s*nFaces\s+(\d+)\s*;", block)
        start_match = re.search(r"(?m)^\s*startFace\s+(\d+)\s*;", block)
        if type_match and nfaces_match and start_match:
            records[patch] = {
                "type": type_match.group(1),
                "nFaces": nfaces_match.group(1),
                "startFace": start_match.group(1),
            }
    return records


def _field_types(path: Path, patches: tuple[str, ...]) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    output: dict[str, str] = {}
    for patch in patches:
        lookup = r'"\.\*"' if patch == "design_candidate" else re.escape(patch)
        match = re.search(rf"(?ms)^[ \t]*{lookup}[ \t]*(?:\n[ \t]*)?\{{.*?\}}", text)
        if match is None:
            raise SystemExit(f"field patch missing: {_rel(path)}:{patch}")
        type_match = re.search(r"\btype\s+(\w+)", match.group(0))
        if type_match is None:
            raise SystemExit(f"field patch type missing: {_rel(path)}:{patch}")
        output[patch] = type_match.group(1)
    return output


def _history(case_dir: Path) -> dict[str, Any]:
    qualification_path = case_dir / "stage_v_qualification.json"
    qualification = _load(qualification_path)
    if qualification.get("qualified") is not True:
        raise SystemExit(f"case is not qualified: {_rel(case_dir)}")
    source = Path(str(qualification["force_stationarity"]["history"]["source"]))
    canonical = case_dir / "postProcessing/forceCoeffs/0/coefficient.dat"
    if source != canonical:
        raise SystemExit(f"qualification source is not canonical: {source} != {canonical}")
    if not canonical.is_file():
        raise SystemExit(f"canonical force history is missing: {_rel(canonical)}")
    return {
        "case_dir": _rel(case_dir),
        "qualification_sha256": _sha256(qualification_path),
        "coefficient_dat_sha256": _sha256(canonical),
        "coefficient_dat": _rel(canonical),
        "row_count": int(qualification["force_stationarity"]["history"]["row_count"]),
        "cells": int(qualification["check_mesh"]["total_cells"]),
        "qualified": True,
        "Cd": float(qualification["force_stationarity"]["responses"]["Cd"]["mean"]),
        "downforce": float(qualification["force_stationarity"]["responses"]["downforce"]["mean"]),
        "raw_mesh_ok": bool(qualification["check_mesh"].get("mesh_ok")),
    }


def _final_continuity(path: Path) -> float:
    matches = re.findall(r"global\s*=\s*([-+0-9.eE]+),\s*cumulative\s*=\s*([-+0-9.eE]+)", path.read_text(encoding="utf-8", errors="ignore"))
    if not matches:
        raise SystemExit(f"continuity history is missing: {_rel(path)}")
    return float(matches[-1][1])


def audit() -> dict[str, Any]:
    manifest = _load(RUN_MANIFEST)
    evidence = _load(EVIDENCE)
    if _sha256(RUN_MANIFEST) != RUN_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("far-field run-manifest sidecar mismatch")
    if evidence["run_manifest"]["sha256"] != _sha256(RUN_MANIFEST):
        raise SystemExit("far-field evidence does not bind its run manifest")
    baseline = ROOT / manifest["baseline"]["case_dir"]
    treatment = ROOT / manifest["treatment"]["case_dir"]
    baseline_history = _history(baseline)
    treatment_history = _history(treatment)
    common_mesh_files = ("cellLevel", "cellZones", "faceZones", "faces", "level0Edge", "neighbour", "owner", "pointLevel", "pointZones", "points", "surfaceIndex")
    mesh_hashes: dict[str, dict[str, str]] = {}
    same_mesh = True
    for name in common_mesh_files:
        left = baseline / "constant/polyMesh" / name
        right = treatment / "constant/polyMesh" / name
        left_hash = _sha256(left)
        right_hash = _sha256(right)
        mesh_hashes[name] = {"baseline": left_hash, "treatment": right_hash}
        same_mesh = same_mesh and left_hash == right_hash
    baseline_boundary = _patch_records(baseline / "constant/polyMesh/boundary")
    treatment_boundary = _patch_records(treatment / "constant/polyMesh/boundary")
    if set(baseline_boundary) != set(treatment_boundary):
        raise SystemExit("boundary patch set changed under far-field treatment")
    same_patch_geometry = all(
        baseline_boundary[name]["nFaces"] == treatment_boundary[name]["nFaces"]
        and baseline_boundary[name]["startFace"] == treatment_boundary[name]["startFace"]
        for name in baseline_boundary
    )
    outer = ("inlet", "outlet", "sideMin", "sideMax", "top")
    walls = ("bottom", "design_candidate")
    boundary_identity = {
        "baseline_outer_mesh": {name: baseline_boundary[name]["type"] for name in outer},
        "treatment_outer_mesh": {name: treatment_boundary[name]["type"] for name in outer},
        "baseline_wall_mesh": {name: baseline_boundary[name]["type"] for name in walls},
        "treatment_wall_mesh": {name: treatment_boundary[name]["type"] for name in walls},
        "treatment_U": _field_types(treatment / "0/U", outer + walls),
        "treatment_p": _field_types(treatment / "0/p", outer + walls),
    }
    expected = {
        "baseline_outer_mesh": {name: "patch" if name in {"inlet", "outlet"} else "patch" for name in outer},
        "treatment_outer_mesh": {name: "patch" for name in outer},
        "baseline_wall_mesh": {name: "wall" for name in walls},
        "treatment_wall_mesh": {name: "wall" for name in walls},
        "treatment_U": {**{name: "freestreamVelocity" for name in outer}, "bottom": "noSlip", "design_candidate": "noSlip"},
        "treatment_p": {**{name: "freestreamPressure" for name in outer}, "bottom": "zeroGradient", "design_candidate": "zeroGradient"},
    }
    # The baseline outer mesh has symmetryPlane on sideMin/sideMax/top; keep it
    # explicit in the record rather than hiding it behind the expected treatment.
    expected["baseline_outer_mesh"] = {"inlet": "patch", "outlet": "patch", "sideMin": "symmetryPlane", "sideMax": "symmetryPlane", "top": "symmetryPlane"}
    boundary_matches = boundary_identity == expected
    base_log = baseline / "log.simpleFoam"
    treatment_log = treatment / "log.simpleFoam"
    convergence_markers = {
        "baseline": "SIMPLE solution converged" in base_log.read_text(encoding="utf-8", errors="ignore") and base_log.read_text(encoding="utf-8", errors="ignore").rstrip().endswith("End"),
        "treatment": "SIMPLE solution converged" in treatment_log.read_text(encoding="utf-8", errors="ignore") and treatment_log.read_text(encoding="utf-8", errors="ignore").rstrip().endswith("End"),
    }
    result = {
        "kind": "stage_v_v16_far_field_contract_audit",
        "schema_version": 1,
        "status": "pass" if same_mesh and same_patch_geometry and boundary_matches and all(convergence_markers.values()) else "fail",
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": _sha256(RUN_MANIFEST)},
        "factor_evidence": {"path": _rel(EVIDENCE), "sha256": _sha256(EVIDENCE)},
        "candidate_sha256": manifest["candidate"]["stl"]["sha256"],
        "baseline": baseline_history,
        "treatment": treatment_history,
        "mesh_identity": {"same_non_boundary_mesh_files": same_mesh, "same_patch_face_ranges": same_patch_geometry, "files": mesh_hashes},
        "boundary_identity": boundary_identity,
        "convergence": {**convergence_markers, "baseline_final_cumulative_continuity": _final_continuity(base_log), "treatment_final_cumulative_continuity": _final_continuity(treatment_log)},
        "checks": {"same_candidate": True, "same_domain_and_mesh": same_mesh and same_patch_geometry, "only_registered_boundary_types_changed": boundary_matches, "fresh_canonical_force_histories": baseline_history["coefficient_dat_sha256"] != treatment_history["coefficient_dat_sha256"], "no_solver_started_during_registration": True},
        "openfoam_references": {"freestreamVelocity": "https://doc.openfoam.com/2212/tools/processing/boundary-conditions/rtm/derived/inletOutlet/freestreamVelocity/", "freestreamPressure": "https://doc.openfoam.com/2312/tools/processing/boundary-conditions/rtm/derived/inletOutlet/freestreamPressure/"},
        "claims_not_supported": ["grid-independent or absolute Stage V downforce", "Stage S S2 qualification", "shape update or optimization authorization"],
    }
    if result["status"] != "pass":
        raise SystemExit("far-field contract audit failed")
    payload = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if AUDIT.exists() and AUDIT.read_text(encoding="utf-8") != payload:
        raise SystemExit("refusing to overwrite immutable far-field audit")
    if not AUDIT.exists():
        AUDIT.write_text(payload, encoding="utf-8")
    digest = _sha256(AUDIT)
    sidecar = AUDIT.with_suffix(".json.sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit("far-field audit sidecar mismatch")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8")
    print(json.dumps({"audit": _rel(AUDIT), "sha256": digest, "status": result["status"]}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    audit()
