#!/usr/bin/env python3
"""Register a solver-free contract and lineage audit for the v16 Stage S path.

This audit deliberately does not compile a case, generate a mesh, or start an
OpenFOAM process.  It binds the v16 candidate to the Stage S baseline and the
reduced-basis contract, records the realized case boundary/mesh contract, and
keeps the unrelated PQ2 candidate as a diagnostic-only reference.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evidence/stage_s_v16_contract_audit_manifest_2026_09.json"
SIDECAR = OUT.with_suffix(".json.sha256")

BASELINE = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"
REDUCED = ROOT / "docs/evidence/stage_s_reduced_basis_fd_manifest_2026_09.json"
WORK_F = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
PQ2 = ROOT / "docs/evidence/stage_v_domain_continuation_manifest_2026_09.json"
PQ2_GRID = ROOT / "docs/evidence/stage_v_fixed_domain_grid_study_2026_09.json"
CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"
CASE_METADATA = CASE / "case_metadata.json"
CASE_QUALIFICATION = CASE / "stage_v_qualification.json"
ORIGINAL_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
REDUCED_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar_reduced_basis_v1.yaml"

V16_CANDIDATE_SHA = "5e6d210794b55a11f3dc76b8be37eeb39d27579b341212939a1c2a63d2fb8d11"
PQ2_CANDIDATE_SHA = "613637cf0fac8bce8a124a479eb3f18417c06995bdbfbe1c99b792fe1db3686e"
OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"
OPENFOAM_IMAGE_ID = "sha256:33fb575aa9980d2bc42fd58c75ae698c489293ba30c991380fe3f899c622f319"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise ValueError(f"required audit input is missing: {rel(path)}")
    return path


def artifact(path: Path, expected_sha: str | None = None) -> dict[str, str]:
    require_file(path)
    observed = sha256_file(path)
    if expected_sha is not None and observed != expected_sha:
        raise ValueError(
            f"hash mismatch for {rel(path)}: expected {expected_sha}, observed {observed}"
        )
    return {"path": rel(path), "sha256": observed}


def pinned_artifact(ref: dict[str, Any]) -> dict[str, str]:
    if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
        raise ValueError(f"invalid pinned artifact reference: {ref!r}")
    return artifact(ROOT / str(ref["path"]), str(ref["sha256"]))


def _named_blocks(text: str) -> dict[str, str]:
    """Read the flat named blocks used by boundary and field dictionaries."""

    pattern = re.compile(
        r"(?ms)^\s*(?:\"(?P<quoted>[^\"]+)\"|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))\s*\{"
        r"(?P<body>.*?)^\s*\}"
    )
    result: dict[str, str] = {}
    for match in pattern.finditer(text):
        name = match.group("quoted") or match.group("plain")
        result[name] = match.group("body")
    return result


def _block_types(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(?m)^\s*(?:\"(?P<quoted>[^\"]+)\"|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))\s*\{\s*"
        r"type\s+(?P<type>[A-Za-z][A-Za-z0-9_]*)\s*;"
    )
    return {
        (match.group("quoted") or match.group("plain")): match.group("type")
        for match in pattern.finditer(text)
    }


def _require_types(actual: dict[str, str], expected: dict[str, str], label: str) -> None:
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise ValueError(f"{label} is missing named patches: {missing}")
    mismatches = {
        name: (expected[name], actual.get(name))
        for name in expected
        if actual.get(name) != expected[name]
    }
    if mismatches:
        raise ValueError(f"{label} boundary type mismatch: {mismatches}")


def _field_patch_types(path: Path) -> dict[str, str]:
    return _block_types(path)


def _resolved_field_type(actual: dict[str, str], patch: str) -> str | None:
    return actual.get(patch) or actual.get(".*")


def _assert_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, observed {actual!r}")


def _assert_close_vectors(label: str, actual: Any, expected: Any, tolerance: float = 1.0e-12) -> None:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        raise ValueError(f"{label} is not a lower/upper mapping")
    for key in ("lower", "upper"):
        av = actual.get(key)
        ev = expected.get(key)
        if not isinstance(av, list) or not isinstance(ev, list) or len(av) != len(ev):
            raise ValueError(f"{label} mismatch at {key}: expected {ev!r}, observed {av!r}")
        if any(abs(float(a) - float(e)) > tolerance for a, e in zip(av, ev)):
            raise ValueError(f"{label} mismatch at {key}: expected {ev!r}, observed {av!r}")


def _canonical_spec_sha(path: Path) -> str:
    # Import lazily so the script remains a simple solver-free audit utility.
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256

    return problem_spec_sha256(load_problem_spec(path))


def build_manifest() -> dict[str, Any]:
    baseline = load_json(require_file(BASELINE))
    reduced = load_json(require_file(REDUCED))
    work_f = load_json(require_file(WORK_F))
    pq2 = load_json(require_file(PQ2))
    pq2_grid = load_json(require_file(PQ2_GRID))
    metadata = load_json(require_file(CASE_METADATA))
    qualification = load_json(require_file(CASE_QUALIFICATION))

    baseline_surface = baseline["handoff"]["artifacts"]["surface_stl"]
    _assert_equal("baseline candidate surface hash", baseline_surface["sha256"], V16_CANDIDATE_SHA)
    candidate_source = ROOT / baseline_surface["path"]
    candidate_source_ref = artifact(candidate_source, V16_CANDIDATE_SHA)

    case_candidate = CASE / "constant/triSurface/design_candidate.stl"
    case_domain = CASE / "constant/triSurface/allowed_design_domain.stl"
    _assert_equal("case candidate hash", sha256_file(require_file(case_candidate)), V16_CANDIDATE_SHA)
    surface_metadata = {item["id"]: item for item in metadata["tri_surface_files"]}
    _assert_equal("case metadata candidate hash", surface_metadata["candidate"]["sha256"], V16_CANDIDATE_SHA)
    domain_source = Path(surface_metadata["design_domain"]["source_path"])
    _assert_equal("case domain source hash", sha256_file(require_file(domain_source)), surface_metadata["design_domain"]["sha256"])
    _assert_equal("case domain staged hash", sha256_file(require_file(case_domain)), surface_metadata["design_domain"]["sha256"])

    original_spec_sha = sha256_file(require_file(ORIGINAL_SPEC))
    reduced_spec_sha = sha256_file(require_file(REDUCED_SPEC))
    _assert_equal("work-F manifest problem-spec hash", work_f["problem_spec"]["sha256"], original_spec_sha)
    _assert_equal("case metadata raw problem-spec source", metadata["source_project"], str(ORIGINAL_SPEC))
    _assert_equal("case metadata canonical problem-spec hash", metadata["problem_spec_sha256"], _canonical_spec_sha(ORIGINAL_SPEC))
    _assert_equal("reduced manifest original spec hash", reduced["inputs"]["original_problem_spec"]["sha256"], original_spec_sha)
    _assert_equal("reduced manifest reduced spec hash", reduced["inputs"]["reduced_basis_problem_spec"]["sha256"], reduced_spec_sha)

    expected_mesh_patches = {
        "inlet": "patch",
        "outlet": "patch",
        "sideMin": "symmetryPlane",
        "sideMax": "symmetryPlane",
        "top": "symmetryPlane",
        "bottom": "wall",
        "design_candidate": "wall",
    }
    boundary_file = CASE / "constant/polyMesh/boundary"
    block_mesh = CASE / "system/blockMeshDict"
    boundary_types = _block_types(require_file(boundary_file))
    block_mesh_types = _block_types(require_file(block_mesh))
    _require_types(boundary_types, expected_mesh_patches, "realized polyMesh boundary")
    _require_types(block_mesh_types, {k: v for k, v in expected_mesh_patches.items() if k != "design_candidate"}, "blockMesh boundary")

    expected_u = {
        "inlet": "fixedValue",
        "outlet": "zeroGradient",
        "sideMin": "symmetryPlane",
        "sideMax": "symmetryPlane",
        "top": "symmetryPlane",
        "bottom": "noSlip",
        "design_candidate": "noSlip",
    }
    expected_p = {
        "inlet": "zeroGradient",
        "outlet": "fixedValue",
        "sideMin": "symmetryPlane",
        "sideMax": "symmetryPlane",
        "top": "symmetryPlane",
        "bottom": "zeroGradient",
        "design_candidate": "zeroGradient",
    }
    u_types = _field_patch_types(require_file(CASE / "0/U"))
    p_types = _field_patch_types(require_file(CASE / "0/p"))
    resolved_u = {name: _resolved_field_type(u_types, name) for name in expected_u}
    resolved_p = {name: _resolved_field_type(p_types, name) for name in expected_p}
    _require_types(resolved_u, expected_u, "U boundaryField")
    _require_types(resolved_p, expected_p, "p boundaryField")

    grid = metadata["grid"]
    bounds = {"lower": list(grid["bounds"][0]), "upper": list(grid["bounds"][1])}
    background = metadata["mesh_refinement"]["background_block_mesh_cells"]
    _assert_close_vectors("work-F expected domain bounds", work_f["expected_case"]["domain_bounds_m"], bounds)
    _assert_equal("work-F expected voxel size", work_f["expected_case"]["voxel_size_m"], grid["spacing"])
    _assert_equal("work-F flow case", work_f["expected_case"]["flow_case_id"], metadata["flow_case_id"])
    _assert_equal("work-F turbulence model", work_f["expected_case"]["turbulence_model"], metadata["operating_point"]["turbulence_model"])
    _assert_equal("work-F force patch", work_f["expected_case"]["force_patch"], metadata["objective"]["force_patches"][0])
    for key, expected in work_f["expected_case"]["operating_point"].items():
        _assert_equal(f"work-F operating point {key}", metadata["operating_point"][key], expected)
    for key, expected in work_f["expected_case"]["force_reference"].items():
        _assert_equal(f"work-F force reference {key}", metadata["force_reference"][key], expected)
    _assert_equal("background block cell total", background["total"], background["nx"] * background["ny"] * background["nz"])

    # PQ2 is intentionally recorded as a non-transferable diagnostic.  The
    # candidate mismatch is a measured identity failure, not an interpretation.
    pq2_sha = pq2["candidate"]["stl"]["sha256"]
    _assert_equal("PQ2 registered candidate hash", pq2_sha, PQ2_CANDIDATE_SHA)
    if pq2_sha == V16_CANDIDATE_SHA:
        raise ValueError("PQ2 diagnostic unexpectedly has the v16 candidate identity")
    _assert_equal("PQ2 grid-study candidate hash", pq2_grid["fixed_conditions"]["candidate_stl_sha256"], PQ2_CANDIDATE_SHA)

    case_files = [
        CASE_METADATA,
        CASE_QUALIFICATION,
        boundary_file,
        block_mesh,
        CASE / "system/snappyHexMeshDict",
        CASE / "0/U",
        CASE / "0/p",
        case_candidate,
        case_domain,
    ]
    evidence_files = [BASELINE, REDUCED, WORK_F, PQ2, PQ2_GRID]
    artifacts = {rel(path): artifact(path) for path in [ORIGINAL_SPEC, REDUCED_SPEC, candidate_source, domain_source, *case_files, *evidence_files]}

    qualification_summary = {
        "profile_id": qualification.get("profile_id"),
        "qualified": qualification.get("qualified"),
        "raw_check_mesh_mesh_ok": qualification.get("check_mesh", {}).get("mesh_ok"),
        "check_mesh_profile_qualified": qualification.get("check_mesh", {}).get("qualified"),
        "concave_cell_fraction": qualification.get("check_mesh", {}).get("concave_cell_fraction"),
        "solver_iterations": qualification.get("solver", {}).get("iteration_count"),
        "interpretation": "profile-qualified case; raw checkMesh mesh_ok=false is retained and is not a clean mesh claim",
    }

    return {
        "schema_version": 1,
        "kind": "stage_s_v16_contract_audit_manifest",
        "immutable": True,
        "status": "registered_solver_free_audit",
        "registered_before_computation": True,
        "evidence_class": "contract",
        "created": "2026-09-25",
        "candidate_binding": {
            "stage_t_terminal_label": baseline["candidate"]["label"],
            "stage_t_surface": candidate_source_ref,
            "stage_s_baseline": {"path": rel(BASELINE), "sha256": sha256_file(BASELINE)},
            "stage_s_case_candidate": artifact(case_candidate, V16_CANDIDATE_SHA),
            "same_candidate": True,
            "candidate_sha256": V16_CANDIDATE_SHA,
            "mismatch_with_pq2_candidate": {"pq2_candidate_sha256": PQ2_CANDIDATE_SHA, "same_candidate": False},
        },
        "problem_spec": {
            "original": {"path": rel(ORIGINAL_SPEC), "file_sha256": original_spec_sha, "canonical_sha256": _canonical_spec_sha(ORIGINAL_SPEC)},
            "reduced_basis": {"path": rel(REDUCED_SPEC), "file_sha256": reduced_spec_sha, "contract_sha256": reduced["inputs"]["reduced_basis_problem_spec"]["sha256"]},
            "case_metadata_canonical_sha256": metadata["problem_spec_sha256"],
            "declared_boundary_scope": "ProblemSpec declares inlet/outlet roles; six-patch Stage S realization is recorded separately until promoted to an explicit versioned boundary contract",
        },
        "mesh_contract": {
            "domain_bounds_m": bounds,
            "voxel_size_m": grid["spacing"],
            "cell_shape": grid["shape"],
            "background_block_mesh_cells": background,
            "case_path": rel(CASE),
            "qualification": qualification_summary,
        },
        "boundary_contract": {
            "realized_mesh": expected_mesh_patches,
            "realized_fields": {"U": resolved_u, "p": resolved_p},
            "nominal_semantics": {
                "inlet": "patch / U fixedValue freestream / p zeroGradient",
                "outlet": "patch / U zeroGradient / p fixedValue",
                "sideMin": "symmetryPlane",
                "sideMax": "symmetryPlane",
                "top": "symmetryPlane",
                "bottom": "wall / U noSlip / p zeroGradient",
                "design_candidate": "wall / U noSlip / p zeroGradient",
            },
            "explicit_problem_spec_six_patch_contract": False,
            "promotion_required_before_reference_campaign": True,
        },
        "stage_s_local_derivative_path": {
            "contract": {"manifest": rel(REDUCED), "sha256": sha256_file(REDUCED)},
            "scope": "reduced-basis centered FD on the v16 Work F case",
            "absolute_downforce_reference": False,
            "grid_independent_claim": False,
        },
        "stage_v_absolute_reference_path": {
            "pq2_evidence": {"manifest": rel(PQ2), "sha256": sha256_file(PQ2), "same_candidate": False},
            "grid_study": {"path": rel(PQ2_GRID), "sha256": sha256_file(PQ2_GRID), "same_candidate": False},
            "transfer_to_v16": "forbidden_until_v16_specific_domain_and_boundary_contract_passes",
        },
        "artifacts": artifacts,
        "execution": {
            "solver_started": False,
            "mesh_generation_started": False,
            "optimization_campaign_started": False,
            "audit_script": {"path": rel(Path(__file__)), "sha256": sha256_file(Path(__file__))},
            "openfoam_image": OPENFOAM_IMAGE,
            "openfoam_image_id": OPENFOAM_IMAGE_ID,
        },
        "claims_supported": [
            "the v16 Stage S candidate, reduced-basis contract, Work F case, and realized six-patch boundary/mesh files are hash-bound",
            "the PQ2 diagnostic candidate is a different STL and is not transferable to v16",
            "the Work F case is profile-qualified while its raw checkMesh mesh_ok=false state remains explicit",
        ],
        "claims_not_supported": [
            "Stage S reduced-basis derivative qualification",
            "an accepted shape update or optimization campaign",
            "grid-independent or absolute Stage V downforce for v16",
            "full-vehicle or high-Re FSAE qualification",
        ],
        "stop_conditions": [
            "any pinned artifact hash mismatch",
            "candidate identity mismatch between v16 baseline, case, and source STL",
            "missing or changed six-patch boundary/field contract",
            "starting S2 before a v16-specific Stage V domain/boundary contract is registered and passed",
            "using PQ2 results as a v16 absolute reference despite candidate mismatch",
        ],
        "next_actions": [
            "register and audit a v16-specific factor-resolved Stage V domain/boundary contract",
            "decide whether the local reduced-basis FD path may run under a clearly local, non-absolute interpretation",
            "only after the applicable contract passes, run the smallest pre-registered solver family; do not start full optimization or a shape update",
        ],
    }


def write_immutable(manifest: dict[str, Any], output: Path = OUT) -> str:
    payload = json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if output.exists():
        if output.read_text(encoding="utf-8") != payload:
            raise ValueError(f"refusing to overwrite immutable artifact: {rel(output)}")
    else:
        output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    sidecar = output.with_suffix(".json.sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise ValueError(f"refusing to overwrite immutable sidecar: {rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8")
    return digest


def main() -> int:
    manifest = build_manifest()
    digest = write_immutable(manifest)
    print(json.dumps({"manifest": rel(OUT), "sha256": digest, "solver_started": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
