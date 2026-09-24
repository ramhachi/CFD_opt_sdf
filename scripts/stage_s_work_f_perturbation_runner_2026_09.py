"""Work F morpher perturbation runner (Slice B): 32 pair-side preflights.

Builds the registered ``moveControlPoints`` utility once, then for every
registered direction/epsilon/sign copies the qualified V1 baseline case,
applies the prescribed control-point movement through the registered
volumetricBSplines morpher, runs ``checkMesh`` on the moved mesh, and records
the pair-side geometry, immobility and mesh gates. No ``simpleFoam`` primal
runs here; the shared centered-FD catalog (Slice C) starts only after all 32
sides pass.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.fixed_grid_contract import CartesianCellGrid  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.stage_s_adjoint_case import build_dynamic_mesh_dict  # noqa: E402
from cfd_sdf.stage_s_perturbation import (  # noqa: E402
    build_control_point_movement,
    extract_patch_surface,
    fixed_patch_immobility,
    movement_sha256,
    movement_to_text,
    parse_check_mesh_qualified,
    perturbation_side_id,
    slug,
    surface_geometry_checks,
)

WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
BASE_CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"
TOOLS_DIR = ROOT / "work/stage_s_work_f_v1/tools"
PERTURBATIONS_DIR = ROOT / "work/stage_s_work_f_v1/perturbations"
EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_perturbation_sides_2026_09.json"
UTILITY_SOURCE = ROOT / "openfoam_utils" / "moveControlPoints"
SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
OPENFOAM_IMAGE = "opencfd/openfoam-default:2512"
ALLRUN = """#!/usr/bin/env bash
set -eo pipefail
tools/moveControlPoints | tee log.moveControlPoints
checkMesh -allGeometry -allTopology | tee log.checkMesh
"""


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _build_tool() -> Path:
    """Compile the moveControlPoints utility into the shared tools directory."""

    build_dir = TOOLS_DIR / "build"
    binary = TOOLS_DIR / "moveControlPoints"
    if binary.is_file():
        return binary
    if build_dir.exists():
        shutil.rmtree(build_dir)
    (build_dir / "moveControlPoints" / "Make").mkdir(parents=True)
    shutil.copyfile(
        UTILITY_SOURCE / "moveControlPoints.C",
        build_dir / "moveControlPoints" / "moveControlPoints.C",
    )
    shutil.copyfile(
        UTILITY_SOURCE / "Make" / "options", build_dir / "moveControlPoints" / "Make" / "options"
    )
    (build_dir / "moveControlPoints" / "Make" / "files").write_text(
        "moveControlPoints.C\nEXE = /case/bin/moveControlPoints\n", encoding="utf-8"
    )
    (build_dir / "Allrun").write_text(
        "#!/usr/bin/env bash\n"
        "source /usr/lib/openfoam/openfoam2512/etc/bashrc\n"
        "set -eo pipefail\n"
        "wmake -s moveControlPoints\n",
        encoding="utf-8",
    )
    (build_dir / "Allclean").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    run = run_openfoam_case(
        build_dir, backend="docker", dry_run=False, timeout_seconds=1800, docker_image=OPENFOAM_IMAGE
    )
    if getattr(run, "returncode", None) != 0 or not (build_dir / "bin" / "moveControlPoints").is_file():
        raise SystemExit("moveControlPoints build failed")
    shutil.copyfile(build_dir / "bin" / "moveControlPoints", binary)
    return binary


def _grid(spec) -> CartesianCellGrid:
    bounds = spec.grid.domain_bounds_m
    voxel = float(spec.grid.voxel_size_m)
    shape = tuple(
        int(round((float(bounds.upper[index]) - float(bounds.lower[index])) / voxel))
        for index in range(3)
    )
    return CartesianCellGrid(
        origin=tuple(bounds.lower), spacing=(voxel, voxel, voxel), cell_shape=shape
    )


def run_sides() -> dict:
    if EVIDENCE.exists():
        raise SystemExit("perturbation side evidence already exists")
    qualification = ca.load_json(QUALIFICATION)
    if qualification["summary"].get("perturbation_allowed") is not True:
        raise SystemExit("adjoint qualification did not allow perturbations")
    catalog = ca.load_json(CATALOG)
    work_f = ca.load_json(WORK_F_MANIFEST)
    spec = load_problem_spec(SPEC)
    grid = _grid(spec)
    basis = catalog["shared_catalog"]["surface_basis"]
    epsilons = [float(value) for value in catalog["shared_catalog"]["epsilons_m"]]
    directions = qualification["directions"]
    active_ids = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    tool = _build_tool()
    tool_sha = _sha256(tool)
    if PERTURBATIONS_DIR.exists():
        shutil.rmtree(PERTURBATIONS_DIR)
    PERTURBATIONS_DIR.mkdir(parents=True)
    baseline_patch = extract_patch_surface(BASE_CASE, time_name="constant")
    baseline_points = BASE_CASE / "constant" / "polyMesh" / "points"

    records: dict[str, dict] = {}
    for direction_name, direction in directions.items():
        vector = np.asarray(direction["values"], dtype=np.float64)
        for epsilon in epsilons:
            for sign, label in ((1.0, "plus"), (-1.0, "minus")):
                side_id = perturbation_side_id(direction_name, epsilon, label)
                case_dir = PERTURBATIONS_DIR / f"{direction_name}__eps{slug(epsilon)}__{label}"
                movement = build_control_point_movement(
                    direction=vector,
                    active_var_ids=active_ids,
                    n_control_points=(8, 8, 8),
                    epsilon=epsilon,
                    sign=sign,
                )
                shutil.copytree(BASE_CASE, case_dir)
                (case_dir / "constant" / "dynamicMeshDict").write_text(
                    build_dynamic_mesh_dict(
                        box_min=tuple(float(value) for value in basis["box_m"]["min"]),
                        box_max=tuple(float(value) for value in basis["box_m"]["max"]),
                        n_cps=tuple(int(value) for value in basis["control_points"]),
                        degree=(3, 3, 3),
                    ),
                    encoding="utf-8",
                    newline="\n",
                )
                (case_dir / "constant" / "controlPointsMovement").write_text(
                    movement_to_text(movement), encoding="utf-8", newline="\n"
                )
                (case_dir / "tools").mkdir(exist_ok=True)
                shutil.copyfile(tool, case_dir / "tools" / "moveControlPoints")
                (case_dir / "tools" / "moveControlPoints").chmod(0o755)
                (case_dir / "Allrun").write_text(ALLRUN, encoding="utf-8", newline="\n")
                run = run_openfoam_case(
                    case_dir,
                    backend="docker",
                    dry_run=False,
                    timeout_seconds=1800,
                    docker_image=OPENFOAM_IMAGE,
                )
                moved_points = case_dir / "0" / "polyMesh" / "points"
                log_path = case_dir / "log.checkMesh"
                check_mesh = parse_check_mesh_qualified(
                    log_path.read_text(encoding="utf-8", errors="replace")
                    if log_path.is_file()
                    else "",
                    profile=STAGE_V_QUALIFICATION_PROFILE_V1,
                )
                moved_patch = extract_patch_surface(case_dir, time_name="0")
                geometry = surface_geometry_checks(
                    baseline=baseline_patch, moved=moved_patch, spec=spec, grid=grid
                )
                immobility = fixed_patch_immobility(
                    case_dir=case_dir,
                    baseline_points=baseline_points,
                    moved_points=moved_points,
                )
                records[side_id] = {
                    "direction": direction_name,
                    "epsilon_m": epsilon,
                    "sign": label,
                    "case_dir": str(case_dir.relative_to(ROOT)),
                    "movement_sha256": movement_sha256(movement),
                    "movement_inf_norm_m": float(np.max(np.abs(movement))),
                    "openfoam_run": {
                        "returncode": getattr(run, "returncode", None),
                        "timed_out": getattr(run, "timed_out", None),
                    },
                    "moved_points_sha256": _sha256(moved_points) if moved_points.is_file() else None,
                    "check_mesh": {
                        "qualified": bool(check_mesh.get("qualified")),
                        "total_cells": check_mesh.get("total_cells"),
                        "concave_cell_fraction": check_mesh.get("concave_cell_fraction"),
                        "failed_check_lines": check_mesh.get("failed_check_lines"),
                    },
                    "geometry": geometry,
                    "immobility": immobility,
                    "pass": bool(
                        getattr(run, "returncode", None) == 0
                        and moved_points.is_file()
                        and check_mesh.get("qualified")
                        and geometry["pass"]
                        and immobility["pass"]
                    ),
                }
                print(side_id, records[side_id]["pass"], flush=True)
    evidence = {
        "kind": "stage_s_work_f_perturbation_sides",
        "schema_version": 1,
        "work_f_manifest": {"path": str(WORK_F_MANIFEST.relative_to(ROOT)), "sha256": _sha256(WORK_F_MANIFEST)},
        "catalog": {"path": str(CATALOG.relative_to(ROOT)), "sha256": _sha256(CATALOG)},
        "qualification": {"path": str(QUALIFICATION.relative_to(ROOT)), "sha256": _sha256(QUALIFICATION)},
        "openfoam_image": work_f["openfoam_image"],
        "openfoam_image_id": work_f["openfoam_image_id"],
        "morpher_utility": {
            "source_dir": str(UTILITY_SOURCE.relative_to(ROOT)),
            "source_sha256": _sha256(UTILITY_SOURCE / "moveControlPoints.C"),
            "binary_path": str(tool.relative_to(ROOT)),
            "binary_sha256": tool_sha,
        },
        "baseline_case": {"path": str(BASE_CASE.relative_to(ROOT))},
        "sides": records,
        "summary": {
            "n_sides": len(records),
            "n_pass": sum(1 for record in records.values() if record["pass"]),
            "all_sides_pass": all(record["pass"] for record in records.values()),
            "primal_campaign_allowed": all(record["pass"] for record in records.values()),
            "solver_started": False,
        },
        "claims_supported": [
            "every registered direction/epsilon/sign pair moves the mesh through the registered B-spline morpher with the outer patches fixed",
            "every moved design surface passes the watertight, manifold, self-intersection, volume, width and clearance gates and the registered checkMesh profile",
        ],
        "claims_not_supported": [
            "no perturbation primal has run; no centered-FD value exists",
            "analytic-vs-FD agreement is not established by this artifact",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F morpher perturbation runner")
    parser.add_argument("--run-sides", action="store_true")
    parser.add_argument("--build-tool", action="store_true")
    args = parser.parse_args()
    if args.run_sides:
        run_sides()
    elif args.build_tool:
        tool = _build_tool()
        print(json.dumps({"binary": str(tool.relative_to(ROOT)), "sha256": _sha256(tool)}, indent=2))
    else:
        parser.error("specify --run-sides or --build-tool")


if __name__ == "__main__":
    main()
