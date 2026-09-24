"""Render and structurally preflight the Work F base adjoint case (no solver).

Copies the qualified V1 body-fitted case, renders the two-solver
``adjointOptimisationFoam`` dictionaries with the registered response
directions and the B-spline volume morpher, checks the rendered dictionaries
structurally and with OpenFOAM's dictionary reader, and records the preflight
artifact. The adjoint solve itself is a separate authorized step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.fd_preregistration import read_fd_campaign_manifest  # noqa: E402
from cfd_sdf.stage_s_adjoint_case import (  # noqa: E402
    ADJOINT_SOLVER_NAMES,
    AdjointObjective,
    render_adjoint_case,
    verify_adjoint_case,
    verify_adjoint_case_with_openfoam,
)

WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
SOLVER_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_v1_solver_2026_09.json"
SOURCE_CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"
ADJOINT_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"
ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_adjoint_preflight_2026_09.json"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _objectives(catalog: dict, metadata: dict) -> tuple[AdjointObjective, ...]:
    reference = metadata["force_reference"]
    free_patch = catalog["shared_catalog"]["fixed_regions"]["free_patch"]
    objectives = []
    for response, record in catalog["manifests"].items():
        manifest, _ = read_fd_campaign_manifest(ROOT / record["path"])
        identity = manifest.fixture["response_identity"]
        objectives.append(
            AdjointObjective(
                response=response,
                solver_name=ADJOINT_SOLVER_NAMES[response],
                direction=tuple(float(value) for value in identity["direction"]),
                patches=(free_patch,),
                area_m2=float(reference["area_m2"]),
                rho_inf=float(reference["density_kg_m3"]),
                u_inf=float(reference["freestream_speed_mps"]),
            )
        )
    return tuple(objectives)


def run_preflight() -> dict:
    if ADJOINT_CASE.exists() or ARTIFACT.exists():
        raise SystemExit("Work F adjoint preflight artifacts already exist")
    work_f_sidecar = WORK_F_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if _sha256(WORK_F_MANIFEST) != work_f_sidecar:
        raise SystemExit("Work F manifest sidecar mismatch")
    work_f = ca.load_json(WORK_F_MANIFEST)
    catalog = ca.load_json(CATALOG)
    for response, record in catalog["manifests"].items():
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"{response} surface-FD manifest hash mismatch")
    solver = ca.load_json(SOLVER_EVIDENCE)
    if solver["summary"].get("surface_fd_allowed") is not True:
        raise SystemExit("the V1 baseline did not allow surface FD")
    metadata = ca.load_json(SOURCE_CASE / "case_metadata.json")
    objectives = _objectives(catalog, metadata)
    basis = catalog["shared_catalog"]["surface_basis"]
    render = render_adjoint_case(
        source_case=SOURCE_CASE,
        target_case=ADJOINT_CASE,
        objectives=objectives,
        box_min=tuple(float(value) for value in basis["box_m"]["min"]),
        box_max=tuple(float(value) for value in basis["box_m"]["max"]),
        n_cps=tuple(int(value) for value in basis["control_points"]),
        degree=(3, 3, 3),
        primal_iterations=3000,
        primal_residual=1.0e-6,
        adjoint_iterations=3000,
        adjoint_residual=1.0e-6,
    )
    structural = verify_adjoint_case(ADJOINT_CASE, objectives=objectives)
    openfoam = verify_adjoint_case_with_openfoam(
        ADJOINT_CASE, docker_image=work_f["openfoam_image"]
    )
    artifact = {
        "kind": "stage_s_work_f_adjoint_preflight",
        "schema_version": 1,
        "work_f_manifest": {
            "path": str(WORK_F_MANIFEST.relative_to(ROOT)),
            "sha256": _sha256(WORK_F_MANIFEST),
        },
        "catalog": {"path": str(CATALOG.relative_to(ROOT)), "sha256": _sha256(CATALOG)},
        "solver_evidence": {
            "path": str(SOLVER_EVIDENCE.relative_to(ROOT)),
            "sha256": _sha256(SOLVER_EVIDENCE),
        },
        "source_case": {
            "path": str(SOURCE_CASE.relative_to(ROOT)),
            "case_metadata_sha256": _sha256(SOURCE_CASE / "case_metadata.json"),
        },
        "adjoint_case": {
            "path": str(ADJOINT_CASE.relative_to(ROOT)),
            "optimisation_dict_sha256": _sha256(ADJOINT_CASE / "system" / "optimisationDict"),
            "dynamic_mesh_dict_sha256": _sha256(ADJOINT_CASE / "constant" / "dynamicMeshDict"),
            "objectives": [objective.to_dict() for objective in objectives],
            "box_m": basis["box_m"],
            "control_points": basis["control_points"],
        },
        "structural_checks": structural,
        "openfoam_dictionary_check": openfoam,
        "summary": {
            "preflight_pass": bool(structural["pass"] and openfoam["pass"]),
            "adjoint_allowed": bool(structural["pass"] and openfoam["pass"]),
            "solver_started": False,
        },
        "claims_supported": [
            "the base adjoint dictionaries parse in OpenFOAM and declare the registered drag and downforce solvers with the registered directions, references and B-spline morpher",
        ],
        "claims_not_supported": [
            "no adjoint was solved and no faceSensNormal was exported",
        ],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F base adjoint preflight")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        run_preflight()
    else:
        parser.error("specify --preflight")


if __name__ == "__main__":
    main()
