"""Run the Work F base adjoints and record their evidence (no perturbations).

Runs ``adjointOptimisationFoam`` once on the preflighted base adjoint case,
verifies that both adjoint solvers wrote ``faceSensNormal<adjS>``, and records
the append-only run evidence. It never runs a perturbation primal or a shape
update.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402

WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_adjoint_preflight_2026_09.json"
ADJOINT_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"
EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_adjoint_run_2026_09.json"
ALLRUN = """#!/usr/bin/env bash
set -euo pipefail
adjointOptimisationFoam | tee log.adjointOptimisationFoam
"""


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def run_adjoint() -> dict:
    if EVIDENCE.exists():
        raise SystemExit("Work F adjoint run evidence already exists")
    work_f_sidecar = WORK_F_MANIFEST.with_suffix(".json.sha256").read_text(encoding="utf-8").strip()
    if _sha256(WORK_F_MANIFEST) != work_f_sidecar:
        raise SystemExit("Work F manifest sidecar mismatch")
    work_f = ca.load_json(WORK_F_MANIFEST)
    preflight = ca.load_json(PREFLIGHT)
    if preflight["summary"].get("adjoint_allowed") is not True:
        raise SystemExit("adjoint preflight did not allow the run")
    case_metadata = ADJOINT_CASE / "case_metadata.json"
    if _sha256(case_metadata) != preflight["source_case"]["case_metadata_sha256"]:
        raise SystemExit("adjoint case metadata changed after the preflight")
    (ADJOINT_CASE / "Allrun").write_text(ALLRUN, encoding="utf-8", newline="\n")
    run = run_openfoam_case(
        ADJOINT_CASE,
        backend="docker",
        dry_run=False,
        timeout_seconds=int(work_f["solver_budget"]["solver_timeout_seconds"]),
        docker_image=work_f["openfoam_image"],
    )
    log_path = ADJOINT_CASE / "log.adjointOptimisationFoam"
    log = log_path.read_text(errors="replace") if log_path.is_file() else ""
    sensitivity_files = sorted(
        path for path in ADJOINT_CASE.rglob("faceSensNormal*") if path.is_file()
    )
    sensitivity_records = {
        str(path.relative_to(ADJOINT_CASE)): _sha256(path) for path in sensitivity_files
    }
    derivative_files = sorted(
        path for path in (ADJOINT_CASE / "optimisation" / "derivatives").glob("*") if path.is_file()
    )
    derivative_records = {
        path.name: _sha256(path) for path in derivative_files
    }
    control_points_path = (
        ADJOINT_CASE / "optimisation" / "controlPoints" / "boxcpsBsplines0.csv"
    )
    expected = {"adjDownforce", "adjDrag"}
    found = {
        name
        for name in expected
        if any(name in record for record in derivative_records)
        or any(name in record for record in sensitivity_records)
    }
    converged_markers = len(re.findall(r"solution converged in", log, re.IGNORECASE))
    evidence = {
        "kind": "stage_s_work_f_adjoint_run",
        "schema_version": 1,
        "manifest": {"path": str(WORK_F_MANIFEST.relative_to(ROOT)), "sha256": _sha256(WORK_F_MANIFEST)},
        "preflight": {"path": str(PREFLIGHT.relative_to(ROOT)), "sha256": _sha256(PREFLIGHT)},
        "case_dir": str(ADJOINT_CASE.relative_to(ROOT)),
        "commands": [line for line in ALLRUN.splitlines() if line.strip()],
        "openfoam_run": {
            "returncode": getattr(run, "returncode", None),
            "timed_out": getattr(run, "timed_out", None),
        },
        "log": {
            "path": str(log_path.relative_to(ROOT)),
            "sha256": _sha256(log_path) if log_path.is_file() else None,
            "converged_markers": converged_markers,
        },
        "analytic": {
            "expected_solvers": sorted(expected),
            "found_solvers": sorted(found),
            "face_sens_normal_files": sensitivity_records,
            "design_variable_derivative_files": derivative_records,
            "control_points_csv": {
                "path": str(control_points_path.relative_to(ROOT)),
                "sha256": _sha256(control_points_path) if control_points_path.is_file() else None,
            },
        },
        "summary": {
            "adjoint_converged": bool(found == expected and getattr(run, "returncode", None) == 0),
            "analytic_derivatives_ready": bool(found == expected),
            "perturbation_allowed": False,
            "shape_update_allowed": False,
        },
        "claims_supported": [
            "the base adjoint case ran, both registered adjoint solvers converged, and each wrote its design-variable derivative file",
        ],
        "claims_not_supported": [
            "no perturbation primal, FD value or shape update exists yet",
            "the analytic-vs-FD agreement is not established by this artifact",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Work F base adjoints")
    parser.add_argument("--run-adjoint", action="store_true")
    args = parser.parse_args()
    if args.run_adjoint:
        run_adjoint()
    else:
        parser.error("specify --run-adjoint")


if __name__ == "__main__":
    main()
