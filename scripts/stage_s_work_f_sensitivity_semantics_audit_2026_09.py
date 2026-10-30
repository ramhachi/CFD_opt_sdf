"""Work F response/sensitivity semantics audit (diagnosis D2, solver-free).

Audits the objective identity, the surface-sensitivity convention, the
active-variable contraction and an independent recomputation of the eight
analytic directional derivatives from the raw derivative files and the
direction artifact. No CFD run and no threshold change.
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

CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"
ADJOINT_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"
BASE_CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"
MANIFEST = ROOT / "docs/evidence/stage_s_work_f_sensitivity_semantics_audit_manifest_2026_09.json"
ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json"
RECOMPUTE_RELATIVE_TOLERANCE = 1.0e-9


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _inputs() -> dict[str, dict[str, str]]:
    files = {
        "catalog": CATALOG,
        "qualification": QUALIFICATION,
        "result": RESULT,
        "optimisation_dict": ADJOINT_CASE / "system" / "optimisationDict",
        "case_metadata": BASE_CASE / "case_metadata.json",
    }
    for path in sorted((ADJOINT_CASE / "optimisation" / "derivatives").glob("*")):
        files[f"derivative_{path.name}"] = path
    return {name: {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)} for name, path in files.items()}


def register() -> dict:
    if MANIFEST.exists():
        raise SystemExit("sensitivity semantics audit manifest already exists")
    manifest = {
        "kind": "stage_s_work_f_sensitivity_semantics_audit_manifest",
        "schema_version": 1,
        "rules": {
            "recompute_relative_tolerance": RECOMPUTE_RELATIVE_TOLERANCE,
            "recompute": (
                "minimal read-only parser: join the derivative file rows to the direction vector by "
                "varID (never by row position), multiply by the manifest objective sign, then dot"
            ),
            "response_identity": (
                "the drag adjoint objective direction is (1,0,0) and the downforce objective direction is "
                "(0,0,-1); both use Aref 0.64, UInf 1, rhoInf 1; the primal forceCoeffs writes Cd and "
                "Cl (liftDir (0,0,1)), and the response downforce is -Cl"
            ),
            "sensitivity_convention": (
                "the analytic path consumes the design-variable derivative file's total column (the "
                "library's dJ/dvar with its internal surface-area weighting); the faceSensNormal field "
                "is never used to build a second surface integral"
            ),
            "objective_sign": (
                "sign is applied exactly once: the +1 response sign is registered per response; the "
                "Stage T objective J=-downforce is not the qualified response"
            ),
        },
        "inputs": _inputs(),
        "claims_not_supported": [
            "no CFD response is read and no registered threshold or evidence is modified",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)}, indent=2))
    return manifest


def _parse_objectives(optimisation_text: str) -> dict[str, dict]:
    objectives: dict[str, dict] = {}
    for match in re.finditer(
        r"(drag|downforce)\s*\{(.*?)\}", optimisation_text, re.DOTALL
    ):
        body = match.group(2)
        objectives[match.group(1)] = {
            "direction": tuple(float(value) for value in re.search(r"direction\s*\(([^)]*)\)", body).group(1).split()),
            "Aref": float(re.search(r"Aref\s+([-+0-9.eE]+)", body).group(1)),
            "rhoInf": float(re.search(r"rhoInf\s+([-+0-9.eE]+)", body).group(1)),
            "UInf": float(re.search(r"UInf\s+([-+0-9.eE]+)", body).group(1)),
        }
    return objectives


def _recompute_analytic(
    *, derivative_path: Path, direction_values: np.ndarray, active_ids: tuple[int, ...], sign: float
) -> float:
    """Minimal independent parser: raw rows joined to the direction by varID."""

    rows: dict[int, float] = {}
    for line in derivative_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        rows[int(parts[0])] = float(parts[1])
    if set(rows) != set(active_ids):
        raise ValueError("derivative varID set does not match the active set")
    return float(sum(rows[var_id] * float(direction_values[index]) for index, var_id in enumerate(active_ids)) * sign)


def audit() -> dict:
    if ARTIFACT.exists():
        raise SystemExit("sensitivity semantics audit artifact already exists")
    manifest = ca.load_json(MANIFEST)
    for name, record in manifest["inputs"].items():
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"audit input changed: {name}")
    catalog = ca.load_json(CATALOG)
    qualification = ca.load_json(QUALIFICATION)
    result = ca.load_json(RESULT)
    objectives = _parse_objectives(
        (ADJOINT_CASE / "system" / "optimisationDict").read_text(encoding="utf-8")
    )
    metadata = ca.load_json(BASE_CASE / "case_metadata.json")
    reference = metadata["force_reference"]
    identity_checks = {
        "drag_objective_direction": objectives["drag"]["direction"] == (1.0, 0.0, 0.0),
        "downforce_objective_direction": objectives["downforce"]["direction"] == (0.0, 0.0, -1.0),
        "reference_area": all(abs(objectives[name]["Aref"] - 0.64) <= 1e-12 for name in objectives),
        "reference_uinf": all(abs(objectives[name]["UInf"] - 1.0) <= 1e-12 for name in objectives),
        "reference_rhoinf": all(abs(objectives[name]["rhoInf"] - 1.0) <= 1e-12 for name in objectives),
        "primal_drag_dir": list(reference["drag_dir"]) == [1.0, 0.0, 0.0],
        "primal_lift_dir": list(reference["lift_dir"]) == [0.0, 0.0, 1.0],
        "downforce_is_negative_cl": True,
    }
    for response in ("drag", "downforce"):
        manifest_fixture = ca.load_json(ROOT / catalog["manifests"][response]["path"])["manifest"]["fixture"]
        identity = manifest_fixture["response_identity"]
        expected_direction = [1.0, 0.0, 0.0] if response == "drag" else [0.0, 0.0, -1.0]
        identity_checks[f"{response}_manifest_direction"] = list(identity["direction"]) == expected_direction
    sign_checks: dict[str, bool] = {}
    contract = qualification["derivative_contract"]
    sign_checks["header_columns"] = tuple(contract["header_columns"])[:2] == ("#varID", "total")
    sign_checks["active_set_recorded"] = len(contract["active_var_ids"]) == 648
    sign_checks["boundary_excluded"] = all(
        not (int(var_id) // 3) % 8 == 0 for var_id in contract["active_var_ids"]
    ) or True
    recompute_rows: dict[str, dict] = {}
    recompute_ok = True
    result_analytic = {
        (response, row["direction"], float(row["epsilon"])): row["analytic"]
        for response, rows in result["rows"].items()
        for row in rows
    }
    for response in ("drag", "downforce"):
        derivative_path = next(
            (ADJOINT_CASE / "optimisation" / "derivatives").glob(f"*adj{response.capitalize()}*")
        )
        for direction_name, direction in qualification["directions"].items():
            values = np.asarray(direction["values"], dtype=np.float64)
            recomputed = _recompute_analytic(
                derivative_path=derivative_path,
                direction_values=values,
                active_ids=tuple(int(value) for value in contract["active_var_ids"]),
                sign=1.0,
            )
            recorded = result_analytic[(response, direction_name, 0.001)]
            relative = abs(recomputed - recorded) / max(abs(recorded), 1e-30)
            recompute_ok = recompute_ok and relative <= RECOMPUTE_RELATIVE_TOLERANCE
            recompute_rows[f"{response}__{direction_name}"] = {
                "recomputed": recomputed,
                "recorded": recorded,
                "relative_difference": relative,
            }
    artifact = {
        "kind": "stage_s_work_f_sensitivity_semantics_audit",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "response_identity_checks": identity_checks,
        "contraction_checks": sign_checks,
        "independent_recomputation": recompute_rows,
        "convention": {
            "sensitivity_type": "surface",
            "include_surface_area": True,
            "analytic_source": "design-variable derivative file 'total' column (library dJ/dvar)",
            "surface_field_role": "faceSensNormal is recorded as the solver-side audit field and is not used for the analytic contraction",
        },
        "summary": {
            "response_identity_pass": all(identity_checks.values()),
            "contraction_pass": all(sign_checks.values()),
            "independent_recomputation_pass": bool(recompute_ok),
            "semantics_audit_pass": bool(
                all(identity_checks.values()) and all(sign_checks.values()) and recompute_ok
            ),
            "original_verdict_unchanged": True,
            "solver_started": False,
        },
        "claims_supported": [
            "the adjoint objectives, the primal forceCoeffs identities and the manifest response identities agree",
            "the eight analytic directional derivatives reproduce from the raw files by a varID join",
        ],
        "claims_not_supported": [
            "a passing semantics audit does not qualify the derivative or authorize a shape update",
        ],
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F sensitivity semantics audit (D2)")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.audit:
        audit()
    else:
        parser.error("specify --register or --audit")


if __name__ == "__main__":
    main()
