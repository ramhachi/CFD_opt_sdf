"""Stage S Work F V1 primal baseline run and qualification.

Runs ``simpleFoam`` once on the already-meshed and mesh-qualified V1 case,
writes the registered ``stage_v_qualification_v1`` qualification, and records
the append-only baseline evidence. It does not run an adjoint, a surface FD
campaign or a shape update.
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
from cfd_sdf.cfd import write_stage_v_qualification  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from stage_t_filtered_ramp import SOLVE_ONLY_ALLRUN  # noqa: E402

MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_v1_preflight_2026_09.json"
MESH_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_v1_mesh_2026_09.json"
SOLVER_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_v1_solver_2026_09.json"
CASE_DIR = ROOT / "work/stage_s_work_f_v1/baseline/V1"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def run_solver() -> dict:
    sidecar = MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if _sha256(MANIFEST) != sidecar:
        raise SystemExit("Work F manifest sidecar mismatch")
    manifest = ca.load_json(MANIFEST)
    if ca.python_source_tree_sha256(ROOT / "src/cfd_sdf") != manifest["source_tree_python_sha256"]:
        raise SystemExit("source tree differs from the Work F registration")
    preflight = ca.load_json(PREFLIGHT)
    if preflight["summary"].get("preflight_pass") is not True:
        raise SystemExit("preflight did not pass")
    mesh = ca.load_json(MESH_EVIDENCE)
    if mesh["summary"].get("solver_allowed") is not True:
        raise SystemExit("mesh evidence does not allow the solver")
    if _sha256(CASE_DIR / "case_metadata.json") != preflight["case"]["metadata_sha256"]:
        raise SystemExit("case metadata changed after the preflight")
    if SOLVER_EVIDENCE.exists():
        raise SystemExit("Work F solver evidence already exists")

    (CASE_DIR / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
    run = run_openfoam_case(
        CASE_DIR,
        backend="docker",
        dry_run=False,
        timeout_seconds=int(manifest["solver_budget"]["solver_timeout_seconds"]),
        docker_image=manifest["openfoam_image"],
    )
    qualification_path = write_stage_v_qualification(CASE_DIR)
    qualification = ca.load_json(qualification_path)
    run_summary_path = CASE_DIR / "openfoam_run_summary.json"
    solver_log = CASE_DIR / "log.simpleFoam"
    force_history = CASE_DIR / "postProcessing" / "forceCoeffs" / "0" / "coefficient.dat"
    qualified = bool(qualification.get("qualified"))
    evidence = {
        "kind": "stage_s_work_f_v1_solver",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "mesh_evidence": {"path": str(MESH_EVIDENCE.relative_to(ROOT)), "sha256": _sha256(MESH_EVIDENCE)},
        "case_dir": str(CASE_DIR.relative_to(ROOT)),
        "commands": [line for line in SOLVE_ONLY_ALLRUN.splitlines() if line.strip()],
        "openfoam_run": {
            "returncode": getattr(run, "returncode", None),
            "timed_out": getattr(run, "timed_out", None),
            "summary_path": str(run_summary_path.relative_to(ROOT)),
            "summary_sha256": _sha256(run_summary_path) if run_summary_path.is_file() else None,
        },
        "artifacts": {
            "solver_log": {
                "path": str(solver_log.relative_to(ROOT)),
                "sha256": _sha256(solver_log) if solver_log.is_file() else None,
            },
            "force_history": {
                "path": str(force_history.relative_to(ROOT)),
                "sha256": _sha256(force_history) if force_history.is_file() else None,
            },
            "stage_v_qualification": {
                "path": str(qualification_path.relative_to(ROOT)),
                "sha256": _sha256(qualification_path),
            },
        },
        "qualification": qualification,
        "response_identities": manifest["response_identities"],
        "summary": {
            "solver_profile_qualified": qualified,
            "check_mesh_qualified": bool(qualification.get("check_mesh", {}).get("qualified")),
            "solver_converged": bool(qualification.get("solver", {}).get("qualified")),
            "force_stationarity": bool(qualification.get("force_stationarity", {}).get("qualified")),
            "p17_solver_execution_reconfirmed": bool(
                qualified
                and preflight["clearance"]["qualified"]
                and getattr(run, "returncode", None) == 0
            ),
            "surface_fd_allowed": qualified,
            "shape_update_allowed": False,
        },
        "claims_supported": [
            "the V1 body-fitted baseline case solved to the registered convergence and force-stationarity profile",
            "the exact registered surface ran under solver execution with the clearance preflight pass (P17 closure condition)",
        ],
        "claims_not_supported": [
            "no surface derivative, adjoint or shape update is qualified by this artifact",
            "no grid independence, target-physics or full-vehicle claim",
        ],
    }
    SOLVER_EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage S Work F V1 primal baseline runner")
    parser.add_argument("--run-solver", action="store_true")
    args = parser.parse_args()
    if args.run_solver:
        run_solver()
    else:
        parser.error("specify --run-solver")


if __name__ == "__main__":
    main()
