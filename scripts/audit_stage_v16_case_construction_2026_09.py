#!/usr/bin/env python3
"""Audit the already-run v16 outer-condition cases without launching a solver.

The v16 domain ladder and mixed far-field run are diagnostic evidence only.  This
audit checks the construction that produced those results: ProblemSpec binding,
generated OpenFOAM dictionaries, force-patch/reference semantics, ground and
domain placement, and the final boundary fluxes written by the existing runs.
It intentionally reads existing files only and fails closed on a stale contract
identity or an unexplained flux/force mismatch.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256  # noqa: E402


RUN_MANIFEST = ROOT / "docs/evidence/stage_v_v16_far_field_contract_run_manifest_v2_2026_09.json"
CONTINUATION_MANIFEST = ROOT / "docs/evidence/stage_v_v16_domain_continuation_3p2_run_manifest_2026_09.json"
FAR_FIELD_AUDIT = ROOT / "docs/evidence/stage_v_v16_far_field_contract_audit_2026_09.json"
AUDIT = ROOT / "docs/evidence/stage_v_v16_case_construction_audit_2026_09.json"

PATCHES = ("inlet", "outlet", "sideMin", "sideMax", "top", "bottom", "design_candidate")
OUTER = ("inlet", "outlet", "sideMin", "sideMax", "top")
WALLS = ("bottom", "design_candidate")


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"missing audit input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _float_list(value: Any) -> list[float]:
    return [float(item) for item in value]


def _close(left: Any, right: Any, tolerance: float = 1.0e-10) -> bool:
    left_values = _float_list(left)
    right_values = _float_list(right)
    return len(left_values) == len(right_values) and all(
        math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)
        for a, b in zip(left_values, right_values, strict=True)
    )


def _patch_blocks(text: str, names: tuple[str, ...] = PATCHES) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for name in names:
        match = re.search(
            rf"(?m)^\s*{re.escape(name)}\s*\{{(?P<body>.*?)^\s*\}}",
            text,
            re.DOTALL,
        )
        if match is None:
            raise SystemExit(f"patch {name!r} is missing")
        blocks[name] = match.group("body")
    return blocks


def _field_types(path: Path, names: tuple[str, ...] = PATCHES) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    fallback_match = re.search(r'(?m)^\s*"\.\*"\s*\{(?P<body>.*?)^\s*\}', text, re.DOTALL)
    fallback = fallback_match.group("body") if fallback_match is not None else None
    for name in names:
        match = re.search(
            rf"(?m)^\s*{re.escape(name)}\s*\{{(?P<body>.*?)^\s*\}}",
            text,
            re.DOTALL,
        )
        if match is None:
            if fallback is None:
                raise SystemExit(f"field patch {name!r} is missing in {_rel(path)}")
            blocks[name] = fallback
        else:
            blocks[name] = match.group("body")
    result: dict[str, str] = {}
    for name, body in blocks.items():
        match = re.search(r"(?m)^\s*type\s+(\S+)\s*;", body)
        if match is None:
            raise SystemExit(f"field type is missing for {name} in {_rel(path)}")
        result[name] = match.group(1)
    return result


def _mesh_boundary(path: Path) -> dict[str, dict[str, Any]]:
    blocks = _patch_blocks(path.read_text(encoding="utf-8"))
    records: dict[str, dict[str, Any]] = {}
    for name, body in blocks.items():
        type_match = re.search(r"(?m)^\s*type\s+(\S+)\s*;", body)
        faces_match = re.search(r"(?m)^\s*nFaces\s+(\d+)\s*;", body)
        start_match = re.search(r"(?m)^\s*startFace\s+(\d+)\s*;", body)
        if type_match is None or faces_match is None or start_match is None:
            raise SystemExit(f"incomplete mesh boundary record for {name}")
        records[name] = {
            "type": type_match.group(1),
            "nFaces": int(faces_match.group(1)),
            "startFace": int(start_match.group(1)),
        }
    return records


def _scalar(text: str, key: str) -> float:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s+([-+0-9.eE]+)\s*;", text)
    if match is None:
        raise SystemExit(f"scalar {key!r} is missing")
    return float(match.group(1))


def _dimensioned_scalar(text: str, key: str) -> float:
    match = re.search(
        rf"(?m)^\s*{re.escape(key)}\s+\[[^\]]+\]\s+([-+0-9.eE]+)\s*;",
        text,
    )
    if match is None:
        raise SystemExit(f"dimensioned scalar {key!r} is missing")
    return float(match.group(1))


def _vector(text: str, key: str) -> list[float]:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*\(\s*([^\)]+)\)\s*;", text)
    if match is None:
        raise SystemExit(f"vector {key!r} is missing")
    return [float(value) for value in match.group(1).split()]


def _phi_boundary(path: Path) -> dict[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "boundaryField" not in text:
        raise SystemExit(f"phi boundaryField is missing: {_rel(path)}")
    blocks = _patch_blocks(text[text.index("boundaryField") :])
    result: dict[str, dict[str, Any]] = {}
    for name, body in blocks.items():
        type_match = re.search(r"(?m)^\s*type\s+(\S+)\s*;", body)
        if type_match is None:
            raise SystemExit(f"phi type is missing for {name}")
        list_match = re.search(
            r"nonuniform\s+List<scalar>\s+(\d+)\s*\(\s*(.*?)\s*\)\s*;",
            body,
            re.DOTALL,
        )
        if list_match is None:
            uniform_match = re.search(r"uniform\s+([-+0-9.eE]+)\s*;", body)
            if uniform_match is None:
                raise SystemExit(f"phi value is missing for {name}")
            values = [float(uniform_match.group(1))]
            declared = 1
            representation = "uniform"
        else:
            declared = int(list_match.group(1))
            values = [float(value) for value in list_match.group(2).split()]
            if len(values) != declared:
                raise SystemExit(f"phi list count mismatch for {name}: {len(values)} != {declared}")
            representation = "nonuniform"
        result[name] = {
            "type": type_match.group(1),
            "representation": representation,
            "count": declared,
            "sum": float(sum(values)),
            "min": float(min(values)),
            "max": float(max(values)),
        }
    return result


def _latest_time(case_dir: Path) -> Path:
    times = sorted(
        (path for path in case_dir.iterdir() if path.is_dir() and path.name.isdigit()),
        key=lambda path: int(path.name),
    )
    if not times:
        raise SystemExit(f"no numeric solver output in {_rel(case_dir)}")
    return times[-1]


def _block_mesh_bounds(path: Path) -> tuple[list[float], list[float], list[int]]:
    text = path.read_text(encoding="utf-8")
    vertices_match = re.search(r"vertices\s*\((.*?)\);", text, re.DOTALL)
    block_match = re.search(r"hex\s*\([^\)]*\)\s*\((\d+)\s+(\d+)\s+(\d+)\)", text)
    if vertices_match is None or block_match is None:
        raise SystemExit(f"blockMesh geometry is incomplete: {_rel(path)}")
    vertices = [
        [float(value) for value in match]
        for match in re.findall(r"\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)", vertices_match.group(1))
    ]
    if len(vertices) != 8:
        raise SystemExit(f"expected eight blockMesh vertices, found {len(vertices)}")
    lower = [min(vertex[index] for vertex in vertices) for index in range(3)]
    upper = [max(vertex[index] for vertex in vertices) for index in range(3)]
    counts = [int(value) for value in block_match.groups()]
    return lower, upper, counts


def _location_in_mesh(path: Path) -> list[float]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"locationInMesh\s*\(\s*([^\)]+)\);", text)
    if match is None:
        raise SystemExit(f"locationInMesh is missing: {_rel(path)}")
    return [float(value) for value in match.group(1).split()]


def _registered_boundary_contract(value: str) -> dict[str, str]:
    pieces = [piece.strip() for piece in value.split("/")]
    if len(pieces) == 1:
        return {"mesh": pieces[0], "U": pieces[0], "p": pieces[0]}
    if len(pieces) != 3 or not pieces[1].startswith("U ") or not pieces[2].startswith("p "):
        raise SystemExit(f"unrecognised registered boundary contract: {value!r}")
    return {
        "mesh": pieces[0],
        "U": pieces[1][2:].split()[0],
        "p": pieces[2][2:].split()[0],
    }


def _force_coeffs(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    block_match = re.search(r"(?m)^\s*forceCoeffs\s*\{(?P<body>.*?)^\s*\}", text, re.DOTALL)
    if block_match is None:
        raise SystemExit(f"forceCoeffs function object is missing: {_rel(path)}")
    body = block_match.group("body")
    patches_match = re.search(r"(?m)^\s*patches\s*\(([^\)]*)\)\s*;", body)
    if patches_match is None:
        raise SystemExit("forceCoeffs patches are missing")
    patches = patches_match.group(1).split()
    return {
        "patches": patches,
        "rhoInf": _scalar(body, "rhoInf"),
        "magUInf": _scalar(body, "magUInf"),
        "lRef": _scalar(body, "lRef"),
        "Aref": _scalar(body, "Aref"),
        "CofR": _vector(body, "CofR"),
        "dragDir": _vector(body, "dragDir"),
        "liftDir": _vector(body, "liftDir"),
    }


def _case_record(
    case_dir: Path,
    *,
    spec_path: Path,
    candidate_sha: str,
    expected_extension_token: str,
    expected_boundary: dict[str, dict[str, str]],
    expected_force: dict[str, Any],
) -> dict[str, Any]:
    metadata_path = case_dir / "case_metadata.json"
    metadata = _load(metadata_path)
    source_project = Path(str(metadata["source_project"])).resolve()
    spec = load_problem_spec(spec_path)
    canonical_spec_sha = problem_spec_sha256(spec)
    mesh_boundary = _mesh_boundary(case_dir / "constant/polyMesh/boundary")
    u_types = _field_types(case_dir / "0/U")
    p_types = _field_types(case_dir / "0/p")
    actual_boundary = {
        patch: {
            "mesh": mesh_boundary[patch]["type"],
            "U": u_types[patch],
            "p": p_types[patch],
        }
        for patch in PATCHES
    }
    boundary_matches = actual_boundary == expected_boundary

    block_lower, block_upper, block_counts = _block_mesh_bounds(case_dir / "system/blockMeshDict")
    spec_bounds = spec.grid.domain_bounds_m
    expected_lower = list(spec_bounds.lower)
    expected_upper = list(spec_bounds.upper)
    location = _location_in_mesh(case_dir / "system/snappyHexMeshDict")
    location_inside = all(
        lower < point < upper
        for point, lower, upper in zip(location, expected_lower, expected_upper, strict=True)
    )

    transport = (case_dir / "constant/transportProperties").read_text(encoding="utf-8")
    turbulence = (case_dir / "constant/turbulenceProperties").read_text(encoding="utf-8")
    flow = spec.flow_cases[0]
    velocity = _float_list(flow.freestream_velocity_mps)
    density = float(flow.fluid.density_kg_m3)
    viscosity = float(flow.fluid.dynamic_viscosity_pa_s)
    actual_nu = _dimensioned_scalar(transport, "nu")
    operating_matches = {
        "velocity": math.isclose(float(metadata["operating_point"]["velocity_mps"]), math.sqrt(sum(v * v for v in velocity)), rel_tol=1e-10),
        "density": math.isclose(float(metadata["operating_point"]["density"]), density, rel_tol=1e-10),
        "viscosity": math.isclose(float(metadata["operating_point"]["viscosity"]), viscosity / density, rel_tol=1e-10),
        "transport_nu": math.isclose(actual_nu, viscosity / density, rel_tol=1e-10),
        "turbulence": "simulationType laminar" in turbulence and metadata["operating_point"]["turbulence_model"] == flow.turbulence.model,
    }

    force = _force_coeffs(case_dir / "system/controlDict")
    force_reference = metadata["force_reference"]
    force_matches = {
        "patches": force["patches"] == expected_force["patches"] == metadata["objective"]["force_patches"],
        "Aref": math.isclose(force["Aref"], float(force_reference["area_m2"]), rel_tol=1e-10),
        "lRef": math.isclose(force["lRef"], float(force_reference["length_m"]), rel_tol=1e-10),
        "CofR": _close(force["CofR"], force_reference["moment_center_m"]),
        "rhoInf": math.isclose(force["rhoInf"], float(force_reference["density_kg_m3"]), rel_tol=1e-10),
        "magUInf": math.isclose(force["magUInf"], float(force_reference["freestream_speed_mps"]), rel_tol=1e-10),
        "directions": force["dragDir"] == [1.0, 0.0, 0.0] and force["liftDir"] == [0.0, 0.0, 1.0],
    }

    latest = _latest_time(case_dir)
    phi = _phi_boundary(latest / "phi")
    flux_sum = sum(item["sum"] for item in phi.values())
    flux_checks = {
        "global_closure": abs(flux_sum) <= 1.0e-6,
        "inlet_inflow": phi["inlet"]["sum"] < 0.0,
        "outlet_outflow": phi["outlet"]["sum"] > 0.0,
        "ground_zero": abs(phi["bottom"]["sum"]) <= 1.0e-8,
        "candidate_zero": abs(phi["design_candidate"]["sum"]) <= 1.0e-8,
    }
    if expected_boundary["sideMin"]["mesh"] == "symmetryPlane":
        flux_checks["symmetry_zero"] = all(abs(phi[name]["sum"]) <= 1.0e-8 for name in ("sideMin", "sideMax", "top"))
    else:
        flux_checks["freestream_outer_recorded"] = all(math.isfinite(phi[name]["sum"]) for name in OUTER)

    candidate_path = case_dir / "constant/triSurface/design_candidate.stl"
    candidate_hash_matches = _sha256(candidate_path) == candidate_sha
    metadata_checks = {
        "source_project_matches": source_project == spec_path.resolve(),
        "problem_id_matches_source_spec": metadata.get("problem_id") == spec.problem_id,
        "problem_id_contains_registered_extension": expected_extension_token in str(metadata.get("problem_id", "")),
        "problem_spec_hash_matches_source_spec": metadata.get("problem_spec_sha256") == canonical_spec_sha,
        "grid_bounds_match_source_spec": _close(metadata["grid"]["bounds"][0], expected_lower) and _close(metadata["grid"]["bounds"][1], expected_upper),
        "grid_spacing_matches_source_spec": math.isclose(float(metadata["grid"]["spacing"]), float(spec.grid.voxel_size_m), rel_tol=1e-10),
        "candidate_hash_matches": candidate_hash_matches and metadata["tri_surface_files"][0]["sha256"] == candidate_sha,
    }
    case_checks = {
        "metadata": metadata_checks,
        "boundary": {"actual": actual_boundary, "expected": expected_boundary, "matches": boundary_matches},
        "operating_point": operating_matches,
        "force_patch_and_reference": force_matches,
        "ground_and_domain": {
            "block_mesh_lower_matches_spec": _close(block_lower, expected_lower),
            "block_mesh_upper_matches_spec": _close(block_upper, expected_upper),
            "location_in_mesh": location,
            "location_inside_domain": location_inside,
            "bottom_is_wall": mesh_boundary["bottom"]["type"] == "wall",
            "candidate_is_wall": mesh_boundary["design_candidate"]["type"] == "wall",
        },
        "boundary_flux": {
            "latest_time": latest.name,
            "patches": phi,
            "net_flux": flux_sum,
            "checks": flux_checks,
        },
        "qualification": {
            "path": _rel(case_dir / "stage_v_qualification.json"),
            "qualified": bool(_load(case_dir / "stage_v_qualification.json").get("qualified")),
        },
        "block_mesh_counts": block_counts,
    }
    all_metadata = all(metadata_checks.values())
    all_operating = all(operating_matches.values())
    all_force = all(force_matches.values())
    all_ground = all(case_checks["ground_and_domain"][key] for key in ("block_mesh_lower_matches_spec", "block_mesh_upper_matches_spec", "location_inside_domain", "bottom_is_wall", "candidate_is_wall"))
    all_flux = all(flux_checks.values())
    return {
        "case_dir": _rel(case_dir),
        "source_spec": {"path": _rel(spec_path), "problem_id": spec.problem_id, "canonical_sha256": canonical_spec_sha},
        "metadata": {"path": _rel(metadata_path), "sha256": _sha256(metadata_path), "problem_id": metadata.get("problem_id"), "problem_spec_sha256": metadata.get("problem_spec_sha256")},
        "checks": case_checks,
        "pass": all_metadata and boundary_matches and all_operating and all_force and all_ground and all_flux and case_checks["qualification"]["qualified"],
    }


def _write_immutable(path: Path, document: dict[str, Any]) -> str:
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise SystemExit(f"refusing to overwrite immutable audit: {_rel(path)}")
    if not path.exists():
        path.write_text(payload, encoding="utf-8")
    digest = _sha256(path)
    sidecar = path.with_suffix(".json.sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"audit sidecar mismatch: {_rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8")
    return digest


def audit() -> dict[str, Any]:
    run_manifest = _load(RUN_MANIFEST)
    continuation_manifest = _load(CONTINUATION_MANIFEST)
    if _sha256(RUN_MANIFEST) != RUN_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("far-field run manifest sidecar mismatch")
    if _sha256(CONTINUATION_MANIFEST) != CONTINUATION_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip():
        raise SystemExit("+3.2 continuation manifest sidecar mismatch")
    far_field_audit = _load(FAR_FIELD_AUDIT)
    if far_field_audit.get("status") != "pass":
        raise SystemExit("the same-mesh far-field audit must pass before construction audit")

    treatment = run_manifest["treatment"]
    source_case = ROOT / treatment["case_dir"]
    baseline_case = ROOT / run_manifest["baseline"]["case_dir"]
    baseline_metadata = _load(baseline_case / "case_metadata.json")
    spec_path = Path(str(baseline_metadata["source_project"])).resolve()
    if not spec_path.is_file():
        raise SystemExit(f"source ProblemSpec is missing: {spec_path}")
    expected_token_match = re.search(r"\+([0-9]+(?:\.[0-9]+)?)\s*m", treatment["base_domain"])
    if expected_token_match is None:
        raise SystemExit("registered base-domain extension is missing its numeric token")
    expected_extension_token = expected_token_match.group(1).replace(".", "p")
    expected_baseline = {
        patch: _registered_boundary_contract(value)
        for patch, value in continuation_manifest["treatment"]["boundary_contract"].items()
    }
    common = treatment["boundary_contract"]
    expected_mixed = {patch: dict(value) for patch, value in common.items()}
    for patch in treatment["outer_patches"]:
        expected_mixed[patch] = {"mesh": "patch", "U": "freestreamVelocity", "p": "freestreamPressure"}
    expected_force = {"patches": ["design_candidate"]}
    candidate_sha = run_manifest["candidate"]["stl"]["sha256"]
    baseline = _case_record(
        baseline_case,
        spec_path=spec_path,
        candidate_sha=candidate_sha,
        expected_extension_token=expected_extension_token,
        expected_boundary=expected_baseline,
        expected_force=expected_force,
    )
    mixed = _case_record(
        source_case,
        spec_path=spec_path,
        candidate_sha=candidate_sha,
        expected_extension_token=expected_extension_token,
        expected_boundary=expected_mixed,
        expected_force=expected_force,
    )
    blocker_findings: list[str] = []
    for label, record in (("baseline", baseline), ("mixed_far_field", mixed)):
        metadata_checks = record["checks"]["metadata"]
        if not metadata_checks["problem_id_contains_registered_extension"]:
            blocker_findings.append(
                f"{label}: case_metadata.problem_id={record['metadata']['problem_id']!r} does not encode the registered +{expected_extension_token.replace('p', '.')} m case"
            )
    status = "pass" if not blocker_findings and baseline["pass"] and mixed["pass"] else "fail"
    result = {
        "kind": "stage_v_v16_case_construction_audit",
        "schema_version": 1,
        "evidence_class": "diagnostic",
        "status": status,
        "run_manifest": {"path": _rel(RUN_MANIFEST), "sha256": _sha256(RUN_MANIFEST)},
        "continuation_manifest": {"path": _rel(CONTINUATION_MANIFEST), "sha256": _sha256(CONTINUATION_MANIFEST)},
        "far_field_lineage_audit": {"path": _rel(FAR_FIELD_AUDIT), "sha256": _sha256(FAR_FIELD_AUDIT)},
        "registered_extension_token": expected_extension_token,
        "baseline": baseline,
        "mixed_far_field": mixed,
        "findings": blocker_findings,
        "decision": (
            "case construction passes the solver-free audit; no solver run is authorized because the outer-condition response remains a No-Go"
            if status == "pass"
            else "case construction has a provenance blocker; fix the continuation identity guard before registering any new solver contract, and do not rerun OpenFOAM now"
        ),
        "claims_not_supported": [
            "grid-independent or absolute Stage V downforce",
            "Stage S S2 qualification",
            "shape update or optimization authorization",
        ],
        "no_solver_started": True,
    }
    digest = _write_immutable(AUDIT, result)
    print(json.dumps({"audit": _rel(AUDIT), "sha256": digest, "status": status, "findings": blocker_findings}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    audit()
