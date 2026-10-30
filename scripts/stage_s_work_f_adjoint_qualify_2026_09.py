"""Qualify the Work F base-adjoint artifacts and materialize the directions.

Reads the registered adjoint preflight and run evidence, re-parses the solver
log for per-solver convergence and final residuals, parses both design-variable
derivative files and the control-point catalog, materializes the four
registered unit-infinity-norm directions on the active B-spline variable space,
and writes the append-only qualification artifact. ``perturbation_allowed``
remains false unless every base gate passes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.fd_preregistration import read_fd_campaign_manifest  # noqa: E402
from cfd_sdf.stage_s_adjoint_qualification import (  # noqa: E402
    DERIVATIVE_HEADER_COLUMNS,
    active_var_ids,
    build_direction_artifact,
    parse_derivative_file,
    var_id_to_ijk_component,
)

WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_adjoint_preflight_2026_09.json"
RUN_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_adjoint_run_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
ADJOINT_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"
ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
ADJOINT_RESIDUAL_MAX = 1.0e-6
OBJECTIVE_SIGNS = {"drag": 1.0, "downforce": 1.0}

_SOLVER_MARKER = re.compile(r"^(\S+) solution converged in (\d+) iterations", re.MULTILINE)
_RESIDUAL_LINE = re.compile(
    r"Solving for (\w+), Initial residual = ([\d.eE+-]+), Final residual = ([\d.eE+-]+), No Iterations (\d+)"
)
_TIME_LINE = re.compile(r"^Time = (\d+)\s*$", re.MULTILINE)


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _parse_solver_runs(log: str) -> list[dict]:
    runs: list[dict] = []
    last_end = 0
    for match in _SOLVER_MARKER.finditer(log):
        block = log[last_end : match.start()]
        residuals: dict[str, dict] = {}
        for residual in _RESIDUAL_LINE.finditer(block):
            residuals[residual.group(1)] = {
                "initial": float(residual.group(2)),
                "final": float(residual.group(3)),
                "iterations": int(residual.group(4)),
            }
        times = _TIME_LINE.findall(block)
        runs.append(
            {
                "solver": match.group(1),
                "converged_iterations": int(match.group(2)),
                "final_time": int(times[-1]) if times else None,
                "last_residuals": residuals,
            }
        )
        last_end = match.end()
    return runs


def run_qualification() -> dict:
    if ARTIFACT.exists():
        raise SystemExit("adjoint qualification artifact already exists")
    work_f_manifest = ca.load_json(WORK_F_MANIFEST)
    preflight = ca.load_json(PREFLIGHT)
    run_evidence = ca.load_json(RUN_EVIDENCE)
    catalog = ca.load_json(CATALOG)
    if preflight["summary"].get("adjoint_allowed") is not True:
        raise SystemExit("adjoint preflight did not allow the run")
    if run_evidence["summary"].get("analytic_derivatives_ready") is not True:
        raise SystemExit("adjoint run evidence is not analytic-ready")
    log_path = ROOT / run_evidence["log"]["path"]
    if _sha256(log_path) != run_evidence["log"]["sha256"]:
        raise SystemExit("adjoint log hash mismatch")
    log = log_path.read_text(encoding="utf-8", errors="replace")
    solver_runs = _parse_solver_runs(log)
    expected_solvers = ["op1", "adjDownforce", "adjDrag"]
    found_solvers = [run["solver"] for run in solver_runs]
    if found_solvers != expected_solvers:
        raise SystemExit(f"unexpected solver sequence: {found_solvers}")

    derivative_paths = sorted(
        (ADJOINT_CASE / "optimisation" / "derivatives").glob("*")
    )
    derivatives = {
        "drag": parse_derivative_file(
            next(path for path in derivative_paths if "adjDrag" in path.name),
            expected_solver="adjDrag",
        ),
        "downforce": parse_derivative_file(
            next(path for path in derivative_paths if "adjDownforce" in path.name),
            expected_solver="adjDownforce",
        ),
    }
    active_ids = active_var_ids()
    directions = build_direction_artifact(
        drag=derivatives["drag"],
        downforce=derivatives["downforce"],
        active_ids=active_ids,
        random_seeds=(11, 2026),
        objective_signs=OBJECTIVE_SIGNS,
    )

    residual_checks: dict[str, bool] = {}
    residual_maxima: dict[str, float | None] = {}
    for run in solver_runs:
        solver = run["solver"]
        if solver == "op1":
            finals = [
                entry["final"]
                for field, entry in run["last_residuals"].items()
                if field in ("Ux", "Uy", "Uz", "p", "k", "omega", "nut")
            ]
        else:
            finals = [
                entry["final"]
                for field, entry in run["last_residuals"].items()
                if solver in field
            ]
        residual_maxima[solver] = float(max(finals)) if finals else None
        residual_checks[f"{solver}_final_residuals_within_{ADJOINT_RESIDUAL_MAX:g}"] = bool(
            finals and all(value <= ADJOINT_RESIDUAL_MAX for value in finals)
        )
    response_identity_checks: dict[str, bool] = {}
    for response in ("drag", "downforce"):
        record = catalog["manifests"][response]
        manifest, _ = read_fd_campaign_manifest(ROOT / record["path"])
        identity = manifest.fixture["response_identity"]
        response_identity_checks[f"{response}_direction"] = list(identity["direction"]) in (
            [1.0, 0.0, 0.0],
            [0.0, 0.0, -1.0],
        )
        response_identity_checks[f"{response}_manifest_hash"] = (
            _sha256(ROOT / record["path"]) == record["sha256"]
        )
    base_gates = {
        "preflight_allowed": preflight["summary"].get("adjoint_allowed") is True,
        "run_evidence_ready": run_evidence["summary"].get("analytic_derivatives_ready") is True,
        "solver_sequence": found_solvers == expected_solvers,
        "derivative_checks": all(directions["checks"].values()),
        "residual_checks": all(residual_checks.values()),
        "response_identity": all(response_identity_checks.values()),
    }
    perturbation_allowed = all(base_gates.values())
    active_map = {
        str(var_id): var_id_to_ijk_component(var_id) for var_id in active_ids
    }
    artifact = {
        "kind": "stage_s_work_f_adjoint_qualification",
        "schema_version": 1,
        "work_f_manifest": {"path": str(WORK_F_MANIFEST.relative_to(ROOT)), "sha256": _sha256(WORK_F_MANIFEST)},
        "preflight": {"path": str(PREFLIGHT.relative_to(ROOT)), "sha256": _sha256(PREFLIGHT)},
        "run_evidence": {"path": str(RUN_EVIDENCE.relative_to(ROOT)), "sha256": _sha256(RUN_EVIDENCE)},
        "catalog": {"path": str(CATALOG.relative_to(ROOT)), "sha256": _sha256(CATALOG)},
        "openfoam_image": work_f_manifest["openfoam_image"],
        "openfoam_image_id": work_f_manifest["openfoam_image_id"],
        "source_tree_python_sha256": ca.python_source_tree_sha256(ROOT / "src/cfd_sdf"),
        "log": {"path": str(log_path.relative_to(ROOT)), "sha256": _sha256(log_path)},
        "solver_runs": solver_runs,
        "derivative_contract": {
            "header_columns": list(DERIVATIVE_HEADER_COLUMNS),
            "control_point_grid": [8, 8, 8],
            "confinement": "confineBoundaryControlPoints true -> interior control points active",
            "get_cpid_rule": "cp_id = k*nCPsU*nCPsV + j*nCPsU + i; var_id = 3*cp_id + component",
            "active_var_count": len(active_ids),
            "active_var_ids": [int(value) for value in active_ids],
            "var_id_to_ijk_component": active_map,
            "files": {
                response: {
                    "path": str(Path(derivative.path).relative_to(ROOT)),
                    "sha256": derivative.sha256,
                    "final_iteration": derivative.final_iteration,
                    "rows": len(derivative.var_ids),
                    "sign_convention": directions["sign_convention"][response],
                }
                for response, derivative in derivatives.items()
            },
        },
        "directions": directions["directions"],
        "direction_hashes": directions["direction_hashes"],
        "base_gates": base_gates,
        "residual_checks": residual_checks,
        "residual_maxima": residual_maxima,
        "response_identity_checks": response_identity_checks,
        "summary": {
            "adjoint_qualified": perturbation_allowed,
            "perturbation_allowed": perturbation_allowed,
            "shape_update_allowed": False,
        },
        "claims_supported": [
            "both response-specific derivative files match the authoritative active B-spline variable set and the registered sign conventions",
            "the four registered directions are materialized as unit-infinity-norm vectors with recorded hashes",
        ],
        "claims_not_supported": [
            "no perturbation mesh or primal has run; no FD value exists",
            "analytic-vs-FD agreement is not established by this artifact",
        ],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "sha256": _sha256(ARTIFACT),
                "summary": artifact["summary"],
                "direction_hashes": artifact["direction_hashes"],
            },
            indent=2,
        )
    )
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Qualify the Work F base adjoint artifacts")
    parser.add_argument("--qualify", action="store_true")
    args = parser.parse_args()
    if args.qualify:
        run_qualification()
    else:
        parser.error("specify --qualify")


if __name__ == "__main__":
    main()
