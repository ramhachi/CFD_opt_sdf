"""Work F post-D3 diagnosis D4.3 - adjoint-option ablation (adjoint-only).

``--register`` fixes the ablation manifest: the original upwind FD rows and
their pre-registered pass/fail classification, the original adjoint lineage
(optimisationDict, time-500 primal field hashes), the fixed adjoint settings,
the one-factor treatment order and the sole-cause rule.

``--run-surface-area`` executes D4.3a: one independent adjoint lineage with
``includeSurfaceArea false`` while every other option is held at the original
setting. The base primal lineage is re-verified against the original run,
the ablated derivative files are contracted with the four registered
directions, and the result is judged against the pre-registered sole-cause
rule. No perturbation primal is run and no shape update is authorized.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.stage_s_adjoint_qualification import active_var_ids  # noqa: E402
from cfd_sdf.stage_s_component_diagnosis import (  # noqa: E402
    COMPONENT_COLUMNS,
    component_closure,
    contract_columns,
    order_columns,
    parse_derivative_table,
    relative_gate,
)

D4_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json"
D4_1_AUDIT = ROOT / "docs/evidence/stage_s_work_f_derivative_component_audit_2026_09.json"
D4_2_AUDIT = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_audit_2026_09.json"
RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
ORIGINAL_ADJOINT_RUN = ROOT / "docs/evidence/stage_s_work_f_adjoint_run_2026_09.json"
ORIGINAL_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"
ABLATION_ROOT = ROOT / "work/stage_s_work_f_v1/diagnosis/adjoint_ablation"
SURFACE_CASE = ABLATION_ROOT / "surface_area_off"
MESH_MOVEMENT_CASE = ABLATION_ROOT / "mesh_movement_off"
MANIFEST = ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_manifest_2026_09.json"
EVIDENCE_SURFACE_AREA = (
    ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_surface_area_2026_09.json"
)
EVIDENCE_MESH_MOVEMENT = (
    ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_mesh_movement_2026_09.json"
)
DIRECTIONS = (
    "downforce_gradient_aligned",
    "drag_gradient_aligned",
    "random_seed_11",
    "random_seed_2026",
)
ALLRUN = (
    "#!/usr/bin/env bash\n"
    "set -eo pipefail\n"
    "adjointOptimisationFoam | tee log.adjointOptimisationFoam\n"
)
BASELINE_OPTION = "includeSurfaceArea true;"
TREATMENT_OPTION = "includeSurfaceArea false;"
MESH_MOVEMENT_OPTION = "includeMeshMovement false;"
OPTION_PATTERN = r"includeSurfaceArea\s+[^;]+;"
LINEAGE_TIME = "500"
LINEAGE_FIELDS = ("U", "p", "phi")
FACTORS = (
    {
        "order": 1,
        "name": "surface_area",
        "option": "includeSurfaceArea",
        "baseline": "true",
        "treatment": "false",
    },
    {
        "order": 2,
        "name": "mesh_movement",
        "option": "includeMeshMovement",
        "baseline": "true",
        "treatment": "false",
        "conditional": "only if the surface-area ablation does not satisfy the sole-cause rule",
    },
)
FIXED_SETTINGS = {
    "sensitivityType": "surface",
    "smoothSensitivities": "false",
    "shapeType": "volumetricBSplines",
}


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _classification(result: dict, scales: dict[str, float]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for response, response_rows in result["rows"].items():
        floor = 1.0e-3 * abs(scales[response])
        for record in response_rows:
            direction = record["direction"]
            epsilon = float(record["epsilon"])
            row_id = f"{response}__{direction}__{epsilon:g}"
            analytic = float(record["analytic"])
            fd = float(record["fd"])
            ratio, within, sign = relative_gate(analytic, fd)
            rows[row_id] = {
                "response": response,
                "direction": direction,
                "epsilon_m": epsilon,
                "fd": fd,
                "analytic": analytic,
                "ratio": ratio,
                "within_gate": bool(within),
                "sign_agreement": bool(sign),
                "near_zero": bool(abs(analytic) <= floor),
                "noise_floor": floor,
            }
    return rows


def _response_scales() -> dict[str, float]:
    catalog = ca.load_json(CATALOG)
    scales: dict[str, float] = {}
    for response, record in catalog["manifests"].items():
        fixture = ca.load_json(ROOT / record["path"])["manifest"]["fixture"]
        scales[response] = float(fixture["response_scale"])
    return scales


def _lineage_hashes(case_dir: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for name in LINEAGE_FIELDS:
        path = case_dir / LINEAGE_TIME / name
        if not path.is_file():
            raise SystemExit(f"original lineage field is missing: {path}")
        fields[name] = _sha256(path)
    return fields


def register() -> dict:
    if MANIFEST.exists():
        raise SystemExit("adjoint-option diagnostic manifest already exists; refuse overwrite")
    result = ca.load_json(RESULT)
    classification = _classification(result, _response_scales())
    optimisation_dict = ORIGINAL_CASE / "system" / "optimisationDict"
    text = optimisation_dict.read_text(encoding="utf-8")
    if len(re.findall(OPTION_PATTERN, text)) != 1:
        raise SystemExit("the original optimisationDict does not carry exactly one option entry")
    manifest = {
        "kind": "stage_s_work_f_adjoint_option_diagnostic_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "inputs": {
            "component_diagnosis_manifest": {
                "path": str(D4_MANIFEST.relative_to(ROOT)),
                "sha256": _sha256(D4_MANIFEST),
            },
            "component_audit": {"path": str(D4_1_AUDIT.relative_to(ROOT)), "sha256": _sha256(D4_1_AUDIT)},
            "geometry_jacobian_audit": {
                "path": str(D4_2_AUDIT.relative_to(ROOT)),
                "sha256": _sha256(D4_2_AUDIT),
            },
            "surface_fd_result": {"path": str(RESULT.relative_to(ROOT)), "sha256": _sha256(RESULT)},
            "qualification": {"path": str(QUALIFICATION.relative_to(ROOT)), "sha256": _sha256(QUALIFICATION)},
            "original_adjoint_run": {
                "path": str(ORIGINAL_ADJOINT_RUN.relative_to(ROOT)),
                "sha256": _sha256(ORIGINAL_ADJOINT_RUN),
            },
            "work_f_manifest": {"path": str(WORK_F_MANIFEST.relative_to(ROOT)), "sha256": _sha256(WORK_F_MANIFEST)},
        },
        "original_lineage": {
            "case_dir": str(ORIGINAL_CASE.relative_to(ROOT)),
            "optimisationDict_sha256": _sha256(optimisation_dict),
            "time_dir": LINEAGE_TIME,
            "fields": list(LINEAGE_FIELDS),
            "field_hashes": _lineage_hashes(ORIGINAL_CASE),
        },
        "factors": list(FACTORS),
        "fixed_settings": FIXED_SETTINGS,
        "directions": {
            name: ca.load_json(QUALIFICATION)["direction_hashes"][name] for name in DIRECTIONS
        },
        "baseline_row_classification": classification,
        "sole_cause_rule": {
            "relative_gate": 0.05,
            "requirements": [
                "every originally failing row moves within 5% of one",
                "no originally passing row leaves the 5% gate",
                "sign agreement holds for every row",
                "the base primal field and response lineage is unchanged",
                "no row passes because of a near-zero derivative",
            ],
            "note": "the treatment option is never adopted as a production setting by this diagnostic",
        },
        "stop_conditions": [
            "a failed adjoint convergence or lineage gate stops the ablation without a verdict",
            "only one option is changed per ablation and no factor is added after the results",
            "this diagnostic never authorizes a shape update",
        ],
        "claims_not_supported": [
            "this ablation is a diagnostic, not a derivative qualification",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)}, indent=2))
    return manifest


def _verify_inputs(manifest: dict) -> None:
    for name, record in manifest["inputs"].items():
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"registered input changed: {name}")
    lineage = manifest["original_lineage"]
    if _sha256(ROOT / lineage["case_dir"] / "system" / "optimisationDict") != lineage["optimisationDict_sha256"]:
        raise SystemExit("the original optimisationDict changed")
    if _lineage_hashes(ROOT / lineage["case_dir"]) != lineage["field_hashes"]:
        raise SystemExit("the original lineage fields changed")


def _copy_clean_case(case_dir: Path) -> None:
    if case_dir.exists():
        shutil.rmtree(case_dir)
    ABLATION_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ORIGINAL_CASE, case_dir)
    for relative in (
        "optimisation",
        "postProcessing",
        "500",
        "562",
        "log.adjointOptimisationFoam",
        "log.simpleFoam",
        "log.checkMesh",
        "stage_v_qualification.json",
        "stage_v_domain_preflight.json",
        "openfoam_run_summary.json",
    ):
        path = case_dir / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
    (case_dir / "Allrun").write_text(ALLRUN, encoding="utf-8", newline="\n")


def _prepare_surface_area_case() -> dict:
    _copy_clean_case(SURFACE_CASE)
    dictionary = SURFACE_CASE / "system" / "optimisationDict"
    original = dictionary.read_text(encoding="utf-8")
    pattern = re.compile(OPTION_PATTERN)
    if len(pattern.findall(original)) != 1:
        raise SystemExit("the copied optimisationDict does not carry exactly one option entry")
    treated = pattern.sub(TREATMENT_OPTION, original, count=1)
    dictionary.write_text(treated, encoding="utf-8", newline="\n")
    original_lines = set(original.splitlines())
    treated_lines = set(treated.splitlines())
    changed = sorted(treated_lines - original_lines)
    removed = sorted(original_lines - treated_lines)
    isolation = bool(
        len(changed) == 1
        and changed[0].strip() == TREATMENT_OPTION
        and len(removed) == 1
        and removed[0].strip() == BASELINE_OPTION
    )
    if not isolation:
        raise SystemExit("the surface-area treatment is not an isolated single-line change")
    return {"changed_lines": changed, "removed_lines": removed, "isolated": isolation}


def _prepare_mesh_movement_case() -> dict:
    _copy_clean_case(MESH_MOVEMENT_CASE)
    dictionary = MESH_MOVEMENT_CASE / "system" / "optimisationDict"
    original = dictionary.read_text(encoding="utf-8")
    if len(re.findall(OPTION_PATTERN, original)) != 1:
        raise SystemExit("the copied optimisationDict does not carry exactly one option entry")
    if re.search(r"includeMeshMovement\s+[^;]+;", original):
        raise SystemExit("the copied optimisationDict already declares includeMeshMovement")
    treated = original.replace(
        BASELINE_OPTION, BASELINE_OPTION + "\n        includeMeshMovement false;", 1
    )
    dictionary.write_text(treated, encoding="utf-8", newline="\n")
    original_lines = set(original.splitlines())
    treated_lines = set(treated.splitlines())
    changed = sorted(treated_lines - original_lines)
    removed = sorted(original_lines - treated_lines)
    isolation = bool(
        len(changed) == 1
        and changed[0].strip() == MESH_MOVEMENT_OPTION
        and not removed
        and any(line.strip() == BASELINE_OPTION for line in original_lines)
        and any(line.strip() == BASELINE_OPTION for line in treated_lines)
    )
    if not isolation:
        raise SystemExit("the mesh-movement treatment is not an isolated single-line addition")
    return {"changed_lines": changed, "removed_lines": removed, "isolated": isolation}


def _treatment_effect(case_dir: Path) -> dict:
    records: dict[str, dict] = {}
    for path in sorted(ORIGINAL_CASE.rglob("faceSensNormal*")):
        relative = path.relative_to(ORIGINAL_CASE)
        treated = case_dir / relative
        baseline_sha = _sha256(path)
        treated_sha = _sha256(treated) if treated.is_file() else None
        records[str(relative)] = {
            "baseline_sha256": baseline_sha,
            "treatment_sha256": treated_sha,
            "changed": treated_sha != baseline_sha,
        }
    return {
        "face_sens_normal_outputs": records,
        "any_face_sens_normal_changed": bool(any(record["changed"] for record in records.values())),
    }


def _lineage_check(manifest: dict, case_dir: Path, log: str) -> dict:
    lineage = manifest["original_lineage"]
    expected = lineage["field_hashes"]
    actual = _lineage_hashes(case_dir)
    match = {name: actual[name] == expected[name] for name in LINEAGE_FIELDS}
    primal_lines = [line for line in log.splitlines() if "solution converged in" in line and "op1" in line]
    return {
        "time_dir": LINEAGE_TIME,
        "field_hashes_match": match,
        "all_field_hashes_match": bool(all(match.values())),
        "primal_converged_lines": primal_lines,
        "primal_converged": bool(primal_lines),
    }


def _run_ablation(
    *,
    factor: dict,
    case_dir: Path,
    preparation: dict,
    evidence_path: Path,
) -> dict:
    if evidence_path.exists():
        raise SystemExit(f"adjoint-option diagnostic evidence already exists: {evidence_path.name}")
    manifest = ca.load_json(MANIFEST)
    _verify_inputs(manifest)
    work_f = ca.load_json(WORK_F_MANIFEST)
    qualification = ca.load_json(QUALIFICATION)
    active = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    directions = {
        name: np.asarray(entry["values"], dtype=np.float64)
        for name, entry in qualification["directions"].items()
    }
    run = run_openfoam_case(
        case_dir,
        backend="docker",
        dry_run=False,
        timeout_seconds=int(work_f["solver_budget"]["solver_timeout_seconds"]),
        docker_image=work_f["openfoam_image"],
    )
    log_path = case_dir / "log.adjointOptimisationFoam"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    convergence = {
        name: f"{name} solution converged in" in log for name in ("adjDownforce", "adjDrag")
    }
    derivative_paths = sorted((case_dir / "optimisation" / "derivatives").glob("*"))
    tables: dict[str, object] = {}
    for response, solver in (("downforce", "adjDownforce"), ("drag", "adjDrag")):
        matches = [path for path in derivative_paths if solver in path.name]
        if len(matches) != 1:
            raise SystemExit(f"the ablation run did not write exactly one {solver} derivative file")
        tables[response] = parse_derivative_table(matches[0], expected_solver=solver)
    ordered = {response: order_columns(table, active) for response, table in tables.items()}
    lineage = _lineage_check(manifest, case_dir, log)
    effect = _treatment_effect(case_dir)
    original_run = ca.load_json(ORIGINAL_ADJOINT_RUN)["analytic"]["design_variable_derivative_files"]
    derivative_identical = {
        response: bool(
            table.sha256
            == next(
                (
                    sha
                    for name, sha in original_run.items()
                    if response == "downforce" and "adjDownforce" in name
                    or response == "drag" and "adjDrag" in name
                ),
                None,
            )
        )
        for response, table in tables.items()
    }
    rows: dict[str, dict] = {}
    for row_id, baseline in manifest["baseline_row_classification"].items():
        response = baseline["response"]
        direction = baseline["direction"]
        contracted = contract_columns(ordered[response], directions[direction])
        ratio, within, sign = relative_gate(contracted["total"], baseline["fd"])
        rows[row_id] = {
            "response": response,
            "direction": direction,
            "epsilon_m": baseline["epsilon_m"],
            "fd": baseline["fd"],
            "baseline_analytic": baseline["analytic"],
            "ablated_analytic": contracted["total"],
            "baseline_ratio": baseline["ratio"],
            "ablated_ratio": ratio,
            "baseline_within_gate": baseline["within_gate"],
            "ablated_within_gate": bool(within),
            "sign_agreement": bool(sign),
            "near_zero": bool(abs(contracted["total"]) <= baseline["noise_floor"]),
            "components": {
                name: contracted[name] for name in COMPONENT_COLUMNS + ("total",)
            },
            "closure": component_closure(contracted),
        }
    baseline_failing = [row for row in rows.values() if not row["baseline_within_gate"]]
    baseline_passing = [row for row in rows.values() if row["baseline_within_gate"]]
    judgment = {
        "original_failing_rows_all_within": bool(
            baseline_failing and all(row["ablated_within_gate"] for row in baseline_failing)
        ),
        "original_passing_rows_none_worsened": bool(
            all(row["ablated_within_gate"] for row in baseline_passing)
        ),
        "sign_agreement_all": bool(all(row["sign_agreement"] for row in rows.values())),
        "lineage_unchanged": bool(
            lineage["all_field_hashes_match"] and lineage["primal_converged"]
        ),
        "no_near_zero_artifacts": bool(not any(row["near_zero"] for row in rows.values())),
        "n_baseline_failing": len(baseline_failing),
        "n_baseline_passing": len(baseline_passing),
    }
    judgment["sole_cause_supported"] = bool(
        judgment["original_failing_rows_all_within"]
        and judgment["original_passing_rows_none_worsened"]
        and judgment["sign_agreement_all"]
        and judgment["lineage_unchanged"]
        and judgment["no_near_zero_artifacts"]
    )
    run_ok = bool(
        getattr(run, "returncode", None) == 0
        and all(convergence.values())
        and len(tables) == 2
    )
    if not run_ok:
        raise SystemExit(f"the {factor['name']} ablation did not converge; no verdict")
    evidence = {
        "kind": "stage_s_work_f_adjoint_option_diagnostic",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "factor": {
            **factor,
            "fixed_settings": manifest["fixed_settings"],
            "diagnostic_only": True,
        },
        "case_dir": str(case_dir.relative_to(ROOT)),
        "scheme_edit": preparation,
        "treatment_effect": {
            **effect,
            "derivative_files_identical_to_baseline": derivative_identical,
            "derivative_files_changed": {
                response: not identical for response, identical in derivative_identical.items()
            },
        },
        "openfoam_run": {
            "returncode": getattr(run, "returncode", None),
            "timed_out": getattr(run, "timed_out", None),
        },
        "convergence": convergence,
        "derivative_files": {
            response: {"name": Path(table.path).name, "sha256": table.sha256}
            for response, table in tables.items()
        },
        "lineage": lineage,
        "rows": rows,
        "judgment": judgment,
        "summary": {
            "ablation_run_ok": run_ok,
            "sole_cause_supported": judgment["sole_cause_supported"],
            "factor_changes_derivative_files": not all(derivative_identical.values()),
            "next": (
                "D5 independent holdout candidate"
                if judgment["sole_cause_supported"]
                else (
                    "run the includeMeshMovement ablation (D4.3b)"
                    if factor["name"] == "surface_area"
                    else "D4.4 fail-closed: no single option explains the residual"
                )
            ),
            "derivative_qualified": False,
            "shape_update_allowed": False,
            "original_verdict_unchanged": True,
        },
        "claims_supported": [
            "one isolated adjoint-option treatment was run and judged against the pre-registered sole-cause rule",
        ],
        "claims_not_supported": [
            "the treatment is not a production setting and this diagnostic does not qualify the derivative",
        ],
    }
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    print(json.dumps(judgment, indent=2))
    return evidence


def run_surface_area() -> dict:
    return _run_ablation(
        factor={
            "order": 1,
            "name": "surface_area",
            "option": "includeSurfaceArea",
            "baseline": "true",
            "treatment": "false",
        },
        case_dir=SURFACE_CASE,
        preparation=_prepare_surface_area_case(),
        evidence_path=EVIDENCE_SURFACE_AREA,
    )


def run_mesh_movement() -> dict:
    return _run_ablation(
        factor={
            "order": 2,
            "name": "mesh_movement",
            "option": "includeMeshMovement",
            "baseline": "true",
            "treatment": "false",
        },
        case_dir=MESH_MOVEMENT_CASE,
        preparation=_prepare_mesh_movement_case(),
        evidence_path=EVIDENCE_MESH_MOVEMENT,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F post-D3 diagnosis D4.3")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run-surface-area", action="store_true")
    parser.add_argument("--run-mesh-movement", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.run_surface_area:
        run_surface_area()
    elif args.run_mesh_movement:
        run_mesh_movement()
    else:
        parser.error("specify --register, --run-surface-area or --run-mesh-movement")


if __name__ == "__main__":
    main()
