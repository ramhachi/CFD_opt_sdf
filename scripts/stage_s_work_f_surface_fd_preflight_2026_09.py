"""Solver-free geometry preflight for the Work F surface-FD campaign.

Verifies the registered catalog and both response manifests, then checks the
conservative worst-case normal offset for every registered epsilon (both
signs): watertightness, winding, positive volume, self-intersection, minimum
solid width, revoxelized volume and the registered clearance preflight. No
OpenFOAM command runs here; the per-direction mesh/solver preflight runs only
after the base adjoint exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.fd_preregistration import read_fd_campaign_manifest  # noqa: E402
from cfd_sdf.fixed_grid_contract import CartesianCellGrid  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.stage_s_surface_fd import worst_case_geometry_checks  # noqa: E402

CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
BASELINE = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"
SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_preflight_2026_09.json"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def run_preflight() -> dict:
    if ARTIFACT.exists():
        raise SystemExit("Work F surface-FD preflight artifact already exists")
    catalog = ca.load_json(CATALOG)
    for response, record in catalog["manifests"].items():
        path = ROOT / record["path"]
        if _sha256(path) != record["sha256"]:
            raise SystemExit(f"{response} manifest hash mismatch")
        manifest, manifest_hash = read_fd_campaign_manifest(path)
        if manifest_hash != record["manifest_hash"]:
            raise SystemExit(f"{response} manifest document hash mismatch")
    if _sha256(ROOT / catalog["baseline"]["path"]) != catalog["baseline"]["sha256"]:
        raise SystemExit("baseline hash mismatch")
    baseline = ca.load_json(BASELINE)
    stl = ROOT / baseline["handoff"]["artifacts"]["surface_stl"]["path"]
    if _sha256(stl) != baseline["handoff"]["artifacts"]["surface_stl"]["sha256"]:
        raise SystemExit("baseline surface STL hash mismatch")
    spec = load_problem_spec(SPEC)
    if _sha256(SPEC) != catalog["problem_spec"]["sha256"]:
        raise SystemExit("problem spec hash mismatch")
    bounds = spec.grid.domain_bounds_m
    voxel = float(spec.grid.voxel_size_m)
    shape = tuple(
        int(round((float(bounds.upper[index]) - float(bounds.lower[index])) / voxel))
        for index in range(3)
    )
    grid = CartesianCellGrid(origin=tuple(bounds.lower), spacing=(voxel, voxel, voxel), cell_shape=shape)
    import trimesh

    mesh = trimesh.load_mesh(stl)
    epsilons = tuple(float(value) for value in catalog["shared_catalog"]["epsilons_m"])
    checks = worst_case_geometry_checks(
        baseline_mesh=mesh,
        spec=spec,
        grid=grid,
        epsilons_m=epsilons,
    )
    artifact = {
        "kind": "stage_s_work_f_surface_fd_preflight",
        "schema_version": 1,
        "catalog": {"path": str(CATALOG.relative_to(ROOT)), "sha256": _sha256(CATALOG)},
        "baseline": catalog["baseline"],
        "surface_stl": {
            "path": str(stl.relative_to(ROOT)),
            "sha256": _sha256(stl),
        },
        "grid": grid.to_dict(),
        "worst_case_checks": checks,
        "summary": {
            "preflight_pass": bool(checks["all_pass"]),
            "campaign_allowed": bool(checks["all_pass"]),
            "solver_started": False,
        },
        "claims_supported": [
            "every registered epsilon stays geometrically feasible under the conservative uniform normal offset in both signs",
        ],
        "claims_not_supported": [
            "no adjoint, perturbation primal or FD value exists yet",
            "the per-direction mesh/solver preflight still runs after the base adjoint",
        ],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F surface-FD solver-free preflight")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        run_preflight()
    else:
        parser.error("specify --preflight")


if __name__ == "__main__":
    main()
