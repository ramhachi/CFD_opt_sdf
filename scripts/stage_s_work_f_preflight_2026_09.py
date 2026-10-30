"""Stage S Work F0 preflight and mesh-only runner (no simpleFoam).

Verifies the registered Work F baseline manifest, re-runs the
``stage_v_clearance_v1`` domain preflight for the matched-Re laminar problem,
renders the V1 body-fitted case from the registered v16 iso-0.5 surface, and
checks the generated case metadata fail-closed. ``--run-mesh`` then runs the
mesh-only commands and records the parsed ``checkMesh`` verdict; it never
starts ``simpleFoam``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1, evaluate_check_mesh  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256  # noqa: E402
from cfd_sdf.sdf import build_fields  # noqa: E402
from cfd_sdf.stage_v_domain_preflight import (  # noqa: E402
    STAGE_V_CLEARANCE_PROFILE_V1,
    evaluate_stage_v_domain_preflight,
    write_stage_v_domain_preflight_report,
)
from stage_t_filtered_ramp import MESH_ONLY_ALLRUN  # noqa: E402

MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_v1_preflight_2026_09.json"
MESH_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_v1_mesh_2026_09.json"
BASELINE = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"
SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
CASE_DIR = ROOT / "work/stage_s_work_f_v1/baseline/V1"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _verify() -> tuple[dict, dict]:
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if _sha256(MANIFEST) != sidecar:
        raise SystemExit("Work F manifest sidecar mismatch")
    manifest = ca.load_json(MANIFEST)
    if manifest["status"] != "registered_preflight_pending":
        raise SystemExit("Work F manifest is not awaiting its preflight")
    if _sha256(ROOT / manifest["preflight"]["script_path"]) != manifest["preflight"]["script_sha256"]:
        raise SystemExit("Work F preflight script hash mismatch")
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != manifest["source_tree_python_sha256"]:
        raise SystemExit("source tree differs from the Work F registration")
    for key, ref in manifest.get("pinned_evidence", {}).items():
        if _sha256(ROOT / ref["path"]) != ref["sha256"]:
            raise SystemExit(f"pinned evidence mismatch: {key}")
    baseline = ca.load_json(BASELINE)
    if _sha256(BASELINE) != manifest["baseline"]["sha256"]:
        raise SystemExit("baseline artifact hash mismatch")
    if baseline["gate"]["ready_for_stage_s"] is not True:
        raise SystemExit("baseline gate is not ready_for_stage_s=true")
    if baseline["clearance"]["qualified"] is not True:
        raise SystemExit("baseline clearance preflight is not qualified")
    if _sha256(SPEC) != manifest["problem_spec"]["sha256"]:
        raise SystemExit("matched-Re problem spec hash mismatch")
    return manifest, baseline


def _baseline_stl(baseline: dict) -> Path:
    path = ROOT / baseline["handoff"]["artifacts"]["surface_stl"]["path"]
    if _sha256(path) != baseline["handoff"]["artifacts"]["surface_stl"]["sha256"]:
        raise SystemExit("baseline surface STL hash mismatch")
    return path


def _case_checks(manifest: dict, metadata: dict, stl_sha: str, canonical_spec_sha: str) -> dict:
    expected = manifest["expected_case"]
    reference = metadata["force_reference"]
    grid = metadata["grid"]
    checks = {
        "flow_case_id": metadata["flow_case_id"] == expected["flow_case_id"],
        "turbulence_model": metadata["operating_point"]["turbulence_model"] == expected["turbulence_model"],
        "operating_point": all(
            abs(float(metadata["operating_point"][key]) - float(expected["operating_point"][key])) <= 1e-12
            for key in expected["operating_point"]
        ),
        "force_reference": all(
            (
                reference[key] == expected["force_reference"][key]
                if isinstance(expected["force_reference"][key], (int, float))
                else list(reference[key]) == expected["force_reference"][key]
            )
            for key in expected["force_reference"]
        ),
        "force_patch": metadata["objective"]["force_patches"] == [expected["force_patch"]],
        "problem_spec_sha256": metadata.get("problem_spec_sha256") == canonical_spec_sha,
        "candidate_stl": any(
            entry.get("sha256") == stl_sha for entry in metadata["tri_surface_files"]
        ),
        "voxel_size_m": abs(float(metadata["mesh_refinement"]["voxel_size_m"]) - float(expected["voxel_size_m"])) <= 1e-12,
    }
    lower = [float(v) for v in grid["bounds"][0]]
    upper = [float(v) for v in grid["bounds"][1]]
    checks["domain_bounds"] = all(
        abs(lower[index] - float(expected["domain_bounds_m"]["lower"][index])) <= 1e-9
        and abs(upper[index] - float(expected["domain_bounds_m"]["upper"][index])) <= 1e-9
        for index in range(3)
    )
    return checks


def run_preflight() -> dict:
    manifest, baseline = _verify()
    if CASE_DIR.exists() or ARTIFACT.exists():
        raise SystemExit("Work F V1 case or preflight artifact already exists")
    stl = _baseline_stl(baseline)
    stl_sha = _sha256(stl)
    spec = load_problem_spec(SPEC)
    preflight = evaluate_stage_v_domain_preflight(
        spec,
        stl,
        float(manifest["level"]["voxel_size_m"]),
        flow_case_id=manifest["expected_case"]["flow_case_id"],
        profile=STAGE_V_CLEARANCE_PROFILE_V1,
    )
    if not preflight.qualified:
        raise SystemExit(f"clearance preflight failed: {preflight.reasons}")
    cfg = problem_spec_to_project_config(
        spec,
        candidate_stl=stl,
        voxel_size_m=float(manifest["level"]["voxel_size_m"]),
    )
    generate_openfoam_case(cfg, build_fields(cfg), CASE_DIR)
    write_stage_v_domain_preflight_report(CASE_DIR, preflight)
    metadata = ca.load_json(CASE_DIR / "case_metadata.json")
    checks = _case_checks(manifest, metadata, stl_sha, problem_spec_sha256(spec))
    failed = sorted(key for key, value in checks.items() if not value)
    artifact = {
        "kind": "stage_s_work_f_v1_preflight",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "baseline": {"path": str(BASELINE.relative_to(ROOT)), "sha256": _sha256(BASELINE)},
        "problem_spec": {"path": str(SPEC.relative_to(ROOT)), "sha256": _sha256(SPEC)},
        "candidate_stl": {"path": str(stl.relative_to(ROOT)), "sha256": stl_sha},
        "clearance": preflight.to_dict(),
        "case": {
            "case_dir": str(CASE_DIR.relative_to(ROOT)),
            "metadata_sha256": _sha256(CASE_DIR / "case_metadata.json"),
            "checks": checks,
            "failed_checks": failed,
            "pass": not failed,
        },
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "commands": [line for line in MESH_ONLY_ALLRUN.splitlines() if line.strip()],
        "summary": {
            "preflight_pass": not failed,
            "mesh_allowed": not failed,
            "solver_allowed": False,
            "solver_started": False,
        },
        "claims_supported": [
            "the registered v16 iso-0.5 surface renders a body-fitted V1 case whose metadata matches the registered matched-Re laminar operating point and force identities",
            "the fixed-domain clearance preflight passes for the exact registered STL and voxel size",
        ],
        "claims_not_supported": [
            "the mesh has not been generated and checkMesh has not run",
            "simpleFoam is not started and no force or stationarity claim is made",
        ],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def run_mesh() -> dict:
    manifest, _baseline = _verify()
    if not ARTIFACT.is_file():
        raise SystemExit("Work F preflight artifact is missing")
    preflight_artifact = ca.load_json(ARTIFACT)
    if preflight_artifact["summary"].get("mesh_allowed") is not True:
        raise SystemExit("preflight did not allow meshing")
    if _sha256(ROOT / preflight_artifact["case"]["case_dir"] / "case_metadata.json") != preflight_artifact["case"]["metadata_sha256"]:
        raise SystemExit("case metadata changed after the preflight")
    if MESH_EVIDENCE.exists():
        raise SystemExit("Work F mesh evidence already exists")
    (CASE_DIR / "Allrun").write_text(MESH_ONLY_ALLRUN, encoding="utf-8", newline="\n")
    run = run_openfoam_case(
        CASE_DIR,
        backend="docker",
        dry_run=False,
        timeout_seconds=int(manifest["solver_budget"]["mesh_timeout_seconds"]),
        docker_image=manifest["openfoam_image"],
    )
    log_path = CASE_DIR / "log.checkMesh"
    log = log_path.read_text(errors="replace") if log_path.is_file() else ""
    check_mesh = evaluate_check_mesh(log, profile=STAGE_V_QUALIFICATION_PROFILE_V1)
    mesh_qualified = bool(check_mesh.get("qualified"))
    run_summary_path = CASE_DIR / "openfoam_run_summary.json"
    evidence = {
        "kind": "stage_s_work_f_v1_mesh",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "preflight": {"path": str(ARTIFACT.relative_to(ROOT)), "sha256": _sha256(ARTIFACT)},
        "case_dir": str(CASE_DIR.relative_to(ROOT)),
        "commands": [line for line in MESH_ONLY_ALLRUN.splitlines() if line.strip()],
        "openfoam_run": {
            "returncode": getattr(run, "returncode", None),
            "timed_out": getattr(run, "timed_out", None),
            "summary_path": str(run_summary_path.relative_to(ROOT)),
            "summary_sha256": _sha256(run_summary_path) if run_summary_path.is_file() else None,
        },
        "check_mesh": {
            "profile_id": STAGE_V_QUALIFICATION_PROFILE_V1["profile_id"],
            "qualified": mesh_qualified,
            "total_cells": check_mesh.get("total_cells"),
            "failed_check_lines": check_mesh.get("failed_check_lines"),
            "concave_cell_fraction": check_mesh.get("concave_cell_fraction"),
            "raw_log": {"path": str(log_path.relative_to(ROOT)), "sha256": _sha256(log_path) if log_path.is_file() else None},
        },
        "summary": {
            "mesh_profile_qualified": mesh_qualified,
            "solver_allowed": bool(mesh_qualified and getattr(run, "returncode", None) == 0),
            "solver_started": False,
        },
        "claims_supported": [
            "the V1 body-fitted mesh was generated from the registered v16 surface and judged by the registered checkMesh profile",
        ],
        "claims_not_supported": [
            "simpleFoam is not started; no solver, force or stationarity claim is made",
        ],
    }
    MESH_EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage S Work F0 preflight / mesh-only runner")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--run-mesh", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        run_preflight()
    elif args.run_mesh:
        run_mesh()
    else:
        parser.error("specify --preflight or --run-mesh")


if __name__ == "__main__":
    main()
