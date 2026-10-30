"""Work F centered-FD primal campaign (Slice C) and response judgment (Slice D).

Runs the 32 registered perturbation sides sequentially with ``simpleFoam``
(solver-execution allowed only because every side passed the Slice B
preflight), reads both ``Cd`` and downforce from each run, computes the
centered FD per response, and judges drag and downforce separately with the
registered rules. No shape update is authorized by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import write_stage_v_qualification  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.fd_preregistration import read_fd_campaign_manifest  # noqa: E402
from cfd_sdf.stage_s_adjoint_qualification import (  # noqa: E402
    active_var_ids,
    parse_derivative_file,
    response_derivative_vector,
)
from cfd_sdf.stage_s_surface_fd import evaluate_work_f_fd  # noqa: E402
from stage_t_filtered_ramp import SOLVE_ONLY_ALLRUN  # noqa: E402

WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
SIDES = ROOT / "docs/evidence/stage_s_work_f_perturbation_sides_2026_09.json"
RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"
ADJOINT_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"
OBJECTIVE_SIGNS = {"drag": 1.0, "downforce": 1.0}


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _analytic_vectors(active_ids: tuple[int, ...]) -> dict[str, np.ndarray]:
    paths = sorted((ADJOINT_CASE / "optimisation" / "derivatives").glob("*"))
    derivatives = {
        "drag": parse_derivative_file(
            next(path for path in paths if "adjDrag" in path.name), expected_solver="adjDrag"
        ),
        "downforce": parse_derivative_file(
            next(path for path in paths if "adjDownforce" in path.name),
            expected_solver="adjDownforce",
        ),
    }
    return {
        response: response_derivative_vector(
            derivative, active_ids=active_ids, objective_sign=OBJECTIVE_SIGNS[response]
        )
        for response, derivative in derivatives.items()
    }


def _clean_case_for_solver(case_dir: Path) -> None:
    """Remove copied baseline history so only this perturbation run is judged."""

    for relative in (
        "postProcessing",
        "log.simpleFoam",
        "stage_v_qualification.json",
        "constant/dynamicMeshDict",
    ):
        path = case_dir / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
    for child in case_dir.iterdir():
        if child.is_dir() and child.name not in {"0", "constant", "system", "tools"}:
            shutil.rmtree(child)


def run_campaign() -> dict:
    if RESULT.exists():
        raise SystemExit("surface-FD result evidence already exists")
    qualification = ca.load_json(QUALIFICATION)
    sides = ca.load_json(SIDES)
    catalog = ca.load_json(CATALOG)
    work_f = ca.load_json(WORK_F_MANIFEST)
    if qualification["summary"].get("perturbation_allowed") is not True:
        raise SystemExit("adjoint qualification did not allow perturbations")
    if sides["summary"].get("primal_campaign_allowed") is not True:
        raise SystemExit("perturbation sides did not allow the primal campaign")
    active_ids = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    analytic_vectors = _analytic_vectors(active_ids)
    directions = qualification["directions"]
    manifests = {
        response: read_fd_campaign_manifest(
            ROOT / catalog["manifests"][response]["path"]
        )[0]
        for response in ("drag", "downforce")
    }
    timeout = int(work_f["solver_budget"]["solver_timeout_seconds"])

    order = sorted(
        sides["sides"],
        key=lambda side_id: (
            sides["sides"][side_id]["direction"],
            sides["sides"][side_id]["epsilon_m"],
            sides["sides"][side_id]["sign"],
        ),
    )
    run_records: dict[str, dict] = {}
    for side_id in order:
        side = sides["sides"][side_id]
        case_dir = ROOT / side["case_dir"]
        _clean_case_for_solver(case_dir)
        (case_dir / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
        run = run_openfoam_case(
            case_dir,
            backend="docker",
            dry_run=False,
            timeout_seconds=timeout,
            docker_image=work_f["openfoam_image"],
        )
        qualification_path = write_stage_v_qualification(case_dir)
        case_qualification = ca.load_json(qualification_path)
        responses = case_qualification.get("force_stationarity", {}).get("responses", {})
        cd_mean = responses.get("Cd", {}).get("mean")
        downforce_mean = responses.get("downforce", {}).get("mean")
        run_records[side_id] = {
            "direction": side["direction"],
            "epsilon_m": side["epsilon_m"],
            "sign": side["sign"],
            "case_dir": side["case_dir"],
            "openfoam_run": {
                "returncode": getattr(run, "returncode", None),
                "timed_out": getattr(run, "timed_out", None),
            },
            "qualification": {
                "qualified": bool(case_qualification.get("qualified")),
                "solver_converged": bool(case_qualification.get("solver", {}).get("qualified")),
                "force_stationarity": bool(
                    case_qualification.get("force_stationarity", {}).get("qualified")
                ),
                "check_mesh_qualified": bool(
                    case_qualification.get("check_mesh", {}).get("qualified")
                ),
                "reasons": case_qualification.get("reasons"),
            },
            "Cd": cd_mean,
            "downforce": downforce_mean,
            "qualification_path": str(qualification_path.relative_to(ROOT)),
            "qualification_sha256": _sha256(qualification_path),
            "pass": bool(
                getattr(run, "returncode", None) == 0
                and case_qualification.get("qualified")
                and cd_mean is not None
                and downforce_mean is not None
            ),
        }
        print(side_id, run_records[side_id]["pass"], cd_mean, downforce_mean, flush=True)

    rows: dict[str, list[dict]] = {"drag": [], "downforce": []}
    for response in ("drag", "downforce"):
        response_key = "Cd" if response == "drag" else "downforce"
        for direction_name, direction in directions.items():
            vector = np.asarray(direction["values"], dtype=np.float64)
            analytic = float(np.dot(analytic_vectors[response], vector))
            for epsilon in [float(value) for value in catalog["shared_catalog"]["epsilons_m"]]:
                plus = next(
                    (
                        record
                        for record in run_records.values()
                        if record["direction"] == direction_name
                        and record["epsilon_m"] == epsilon
                        and record["sign"] == "plus"
                    ),
                    None,
                )
                minus = next(
                    (
                        record
                        for key, record in run_records.items()
                        if record["direction"] == direction_name
                        and record["epsilon_m"] == epsilon
                        and record["sign"] == "minus"
                    ),
                    None,
                )
                if plus is None or minus is None:
                    raise SystemExit(f"missing perturbation side for {direction_name}/{epsilon}")
                converged = bool(plus["pass"] and minus["pass"])
                fd = None
                if converged:
                    fd = (float(plus[response_key]) - float(minus[response_key])) / (2.0 * epsilon)
                rows[response].append(
                    {
                        "direction": direction_name,
                        "epsilon": epsilon,
                        "analytic": analytic,
                        "fd": fd,
                        "converged": converged,
                        "plus": {
                            "value": plus[response_key],
                            "qualified": plus["pass"],
                        },
                        "minus": {
                            "value": minus[response_key],
                            "qualified": minus["pass"],
                        },
                    }
                )
    verdict = evaluate_work_f_fd(manifests, rows=rows)
    evidence = {
        "kind": "stage_s_work_f_surface_fd_result",
        "schema_version": 1,
        "work_f_manifest": {"path": str(WORK_F_MANIFEST.relative_to(ROOT)), "sha256": _sha256(WORK_F_MANIFEST)},
        "catalog": {"path": str(CATALOG.relative_to(ROOT)), "sha256": _sha256(CATALOG)},
        "qualification": {"path": str(QUALIFICATION.relative_to(ROOT)), "sha256": _sha256(QUALIFICATION)},
        "sides_evidence": {"path": str(SIDES.relative_to(ROOT)), "sha256": _sha256(SIDES)},
        "openfoam_image": work_f["openfoam_image"],
        "openfoam_image_id": work_f["openfoam_image_id"],
        "runs": run_records,
        "rows": rows,
        "response_verdicts": verdict["responses"],
        "summary": {
            "n_runs": len(run_records),
            "n_runs_pass": sum(1 for record in run_records.values() if record["pass"]),
            "both_responses_pass": bool(verdict["both_pass"]),
            "shape_update_allowed": False,
        },
        "claims_supported": [
            "every registered perturbation side ran a converged qualified primal and both responses were read from it",
            "the centered-FD rows are recorded per response with the registered analytic directional derivatives",
        ],
        "claims_not_supported": [
            "a passing surface derivative does not authorize a shape update; a separate one-step manifest is required",
            "no grid-independence, target-physics or full-vehicle claim",
        ],
    }
    RESULT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F centered-FD primal campaign")
    parser.add_argument("--run-campaign", action="store_true")
    args = parser.parse_args()
    if args.run_campaign:
        run_campaign()
    else:
        parser.error("specify --run-campaign")


if __name__ == "__main__":
    main()
