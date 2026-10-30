"""Register the Stage S Work F surface-FD campaign (two response manifests).

Binds the Work F baseline manifest, the registered V1 body-fitted case, the
surface basis, the fixed regions and displacement cap, the dimensionless
epsilon ladder and the four registered directions into two response-specific
immutable FD manifests that share one perturbation catalog. No OpenFOAM run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.fd_preregistration import write_fd_campaign_manifest  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256  # noqa: E402
from cfd_sdf.stage_s_surface_fd import (  # noqa: E402
    build_epsilon_ladder,
    build_work_f_fd_manifests,
    default_fixed_regions,
    default_surface_basis,
)

WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
SOLVER_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_v1_solver_2026_09.json"
BASELINE = ROOT / "docs/evidence/stage_s_baseline_v16_v2_2026_09.json"
SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
MANIFESTS = {
    "drag": ROOT / "docs/evidence/stage_s_work_f_surface_fd_drag_manifest_2026_09.json",
    "downforce": ROOT / "docs/evidence/stage_s_work_f_surface_fd_downforce_manifest_2026_09.json",
}


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _load_mesh(path: Path):
    import trimesh

    return trimesh.load_mesh(path)


def build() -> dict:
    if CATALOG.exists() or any(path.exists() for path in MANIFESTS.values()):
        raise SystemExit("Work F surface-FD registration already exists; refuse overwrite")
    work_f = ca.load_json(WORK_F_MANIFEST)
    sidecar = WORK_F_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if _sha256(WORK_F_MANIFEST) != sidecar:
        raise SystemExit("Work F manifest sidecar mismatch")
    if work_f["status"] != "registered_preflight_pending":
        raise SystemExit("Work F manifest is not registered")
    solver = ca.load_json(SOLVER_EVIDENCE)
    if solver["summary"].get("surface_fd_allowed") is not True:
        raise SystemExit("the V1 baseline did not allow surface FD")
    baseline = ca.load_json(BASELINE)
    if baseline["gate"]["ready_for_stage_s"] is not True:
        raise SystemExit("baseline gate is not ready_for_stage_s=true")
    spec = load_problem_spec(SPEC)
    stl = ROOT / baseline["handoff"]["artifacts"]["surface_stl"]["path"]
    if _sha256(stl) != baseline["handoff"]["artifacts"]["surface_stl"]["sha256"]:
        raise SystemExit("baseline surface STL hash mismatch")
    mesh = _load_mesh(stl)
    ladder = build_epsilon_ladder(float(work_f["level"]["voxel_size_m"]))
    basis = default_surface_basis(np.asarray(mesh.bounds, dtype=np.float64))
    fixed = default_fixed_regions(max(ladder.epsilons_m))
    stationarity = solver["qualification"]["force_stationarity"]["responses"]
    scales = {
        "drag": float(stationarity["Cd"]["mean"]),
        "downforce": float(stationarity["downforce"]["mean"]),
    }
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    manifests = build_work_f_fd_manifests(
        baseline=baseline,
        problem_spec_sha256=problem_spec_sha256(spec),
        level_name=work_f["level"]["name"],
        voxel_size_m=float(work_f["level"]["voxel_size_m"]),
        response_scales=scales,
        basis=basis,
        fixed_regions=fixed,
        ladder=ladder,
        code_commit=commit,
    )
    manifest_hashes: dict[str, str] = {}
    for response, manifest in manifests.items():
        path = write_fd_campaign_manifest(manifest, MANIFESTS[response])
        manifest_hashes[response] = manifest.manifest_hash()
        sidecar_path = MANIFESTS[response].with_suffix(".json.sha256")
        sidecar_path.write_text(_sha256(path) + "\n", encoding="utf-8")
    catalog = {
        "kind": "stage_s_work_f_surface_fd_catalog",
        "schema_version": 1,
        "work_f_manifest": {"path": str(WORK_F_MANIFEST.relative_to(ROOT)), "sha256": _sha256(WORK_F_MANIFEST)},
        "baseline": {"path": str(BASELINE.relative_to(ROOT)), "sha256": _sha256(BASELINE)},
        "solver_evidence": {"path": str(SOLVER_EVIDENCE.relative_to(ROOT)), "sha256": _sha256(SOLVER_EVIDENCE)},
        "problem_spec": {"path": str(SPEC.relative_to(ROOT)), "sha256": _sha256(SPEC)},
        "manifests": {
            response: {
                "path": str(MANIFESTS[response].relative_to(ROOT)),
                "sha256": _sha256(MANIFESTS[response]),
                "manifest_hash": manifest_hashes[response],
            }
            for response in MANIFESTS
        },
        "shared_catalog": {
            "epsilons_m": list(ladder.epsilons_m),
            "epsilon_ratios": list(ladder.ratios),
            "directions": [direction.name for direction in manifests["drag"].directions],
            "surface_basis": basis.to_dict(),
            "fixed_regions": fixed.to_dict(),
        },
        "claims_not_supported": [
            "registration only; no perturbation, adjoint or FD run has executed",
        ],
    }
    CATALOG.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "catalog": str(CATALOG.relative_to(ROOT)),
                "catalog_sha256": _sha256(CATALOG),
                "manifest_hashes": manifest_hashes,
                "epsilons_m": list(ladder.epsilons_m),
            },
            indent=2,
        )
    )
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the Work F surface-FD campaign")
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    if args.register:
        build()
    else:
        parser.error("specify --register")


if __name__ == "__main__":
    main()
