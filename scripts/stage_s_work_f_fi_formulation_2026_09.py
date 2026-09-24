"""Work F post-D4.4 A0/A1 - FI formulation discriminant.

``--register`` (A0, solver-free) fixes the immutable manifest: the D4.x input
hashes, the OpenFOAM image and source hashes of the ``shapeFI``/``surface``
sensitivity classes and the design-variable assembly, the single dictionary
treatment, the fixed primal/mesh/objective/parameterization contract, the
original directions and epsilon ladder, the pre-registered 32-row
classification, and the run budget and stop conditions.

``--run`` (A1, bounded) executes exactly one treatment: one fixed
base/primal lineage with ``adjointOptimisationFoam`` and the two drag and
downforce adjoints, changing only ``sensitivityType surface -> shapeFI``. No
perturbation primal is run; the registered 32-primal FD table is reused. The
FI derivatives are contracted and judged against the pre-registered
sole-cause-style conditions. A pass makes the formulation a D5 holdout
candidate only; the derivative stays unqualified and the shape update stays
blocked.
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
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.stage_s_component_diagnosis import (  # noqa: E402
    COMPONENT_COLUMNS,
    component_closure,
    contract_columns,
    order_columns,
    parse_derivative_table,
    relative_gate,
)
from stage_s_work_f_adjoint_ablation_2026_09 import (  # noqa: E402
    LINEAGE_FIELDS,
    LINEAGE_TIME,
    ORIGINAL_ADJOINT_RUN,
    ORIGINAL_CASE,
    _classification,
    _copy_clean_case,
    _lineage_check,
    _lineage_hashes,
    _response_scales,
    _sha256,
)

POST_D3_PLAN = ROOT / "docs/stage_s_work_f_post_d3_plan_2026_09_25.md"
WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"
COMPONENT_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json"
COMPONENT_AUDIT = ROOT / "docs/evidence/stage_s_work_f_derivative_component_audit_2026_09.json"
JACOBIAN_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_manifest_2026_09.json"
JACOBIAN_AUDIT = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_audit_2026_09.json"
OPTION_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_manifest_2026_09.json"
SURFACE_AREA = ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_surface_area_2026_09.json"
MESH_MOVEMENT = ROOT / "docs/evidence/stage_s_work_f_adjoint_option_diagnostic_mesh_movement_2026_09.json"
FI_ROOT = ROOT / "work/stage_s_work_f_v1/diagnosis/fi_formulation"
FI_CASE = FI_ROOT / "base"
MANIFEST = ROOT / "docs/evidence/stage_s_work_f_fi_formulation_diagnostic_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_fi_formulation_diagnostic_2026_09.json"
DIRECTIONS = (
    "downforce_gradient_aligned",
    "drag_gradient_aligned",
    "random_seed_11",
    "random_seed_2026",
)
BASELINE_SENSITIVITY = "sensitivityType surface;"
TREATMENT_SENSITIVITY = "sensitivityType shapeFI;"
SENSITIVITY_PATTERN = r"sensitivityType\s+[A-Za-z0-9_]+;"
PLATEAU_TOLERANCE = 0.05
RELATIVE_GATE = 0.05
NEAR_ZERO_RELATIVE = 1.0e-3
SOURCE_ROOT = "/usr/lib/openfoam/openfoam2512"
ADJOINT_SENSITIVITY = (
    "src/optimisation/adjointOptimisation/adjoint/optimisation/adjointSensitivity/"
    "adjointSensitivity"
)
SOURCE_FILES = (
    f"{ADJOINT_SENSITIVITY}/shape/FI/sensitivityShapeFI.C",
    f"{ADJOINT_SENSITIVITY}/shape/FI/sensitivityShapeFI.H",
    f"{ADJOINT_SENSITIVITY}/shape/surface/sensitivitySurface.C",
    f"{ADJOINT_SENSITIVITY}/shape/surface/sensitivitySurface.H",
    f"{ADJOINT_SENSITIVITY}/shape/ESI/sensitivityShapeESI.C",
    f"{ADJOINT_SENSITIVITY}/shape/ESI/sensitivityShapeESI.H",
    f"{ADJOINT_SENSITIVITY}/shape/shapeSensitivityBase/ShapeSensitivitiesBase.C",
    f"{ADJOINT_SENSITIVITY}/shape/shapeSensitivityBase/ShapeSensitivitiesBase.H",
    f"{ADJOINT_SENSITIVITY}/adjointSensitivity/adjointSensitivity.C",
    f"{ADJOINT_SENSITIVITY}/adjointSensitivity/adjointSensitivity.H",
    "src/optimisation/adjointOptimisation/adjoint/optimisation/designVariables/shape/"
    "shapeDesignVariables/shapeDesignVariables.C",
    "src/optimisation/adjointOptimisation/adjoint/optimisation/designVariables/shape/"
    "shapeDesignVariables/shapeDesignVariables.H",
)
BUDGET = {
    "fixed_base_primal_lineage_runs": 1,
    "adjoint_runs": 2,
    "new_perturbation_primals": 0,
    "fd_rows_reused": 32,
    "post_hoc_scaling": "forbidden",
    "factor_combination": "forbidden",
    "epsilon_or_tolerance_change": "forbidden",
}


def _source_hashes() -> dict[str, str]:
    import subprocess

    command = " && ".join(f"sha256sum {SOURCE_ROOT}/{path}" for path in SOURCE_FILES)
    completed = subprocess.run(
        ["docker", "run", "--rm", ca.load_json(WORK_F_MANIFEST)["openfoam_image"], "bash", "-lc", command],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(f"source hashing inside the image failed:\n{completed.stderr}")
    records: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        digest, path = parts
        if path.startswith(SOURCE_ROOT + "/"):
            records[str(Path(path).relative_to(SOURCE_ROOT))] = digest
    if len(records) != len(SOURCE_FILES):
        raise SystemExit("not every registered FI source file was hashed inside the image")
    return records


def register() -> dict:
    if MANIFEST.exists():
        raise SystemExit("FI formulation manifest already exists; refuse overwrite")
    work_f = ca.load_json(WORK_F_MANIFEST)
    if work_f.get("profiles", {}).get("surface_fd") is None and work_f.get("openfoam_image") is None:
        raise SystemExit("the Work F manifest lacks the registered image")
    result = ca.load_json(RESULT)
    classification = _classification(result, _response_scales())
    qualification = ca.load_json(QUALIFICATION)
    active = [int(value) for value in qualification["derivative_contract"]["active_var_ids"]]
    optimisation_dict = ORIGINAL_CASE / "system" / "optimisationDict"
    text = optimisation_dict.read_text(encoding="utf-8")
    matches = re.findall(SENSITIVITY_PATTERN, text)
    if len(matches) != 1 or matches[0].strip() != BASELINE_SENSITIVITY:
        raise SystemExit("the original optimisationDict does not declare exactly one surface sensitivity")
    manifest = {
        "kind": "stage_s_work_f_fi_formulation_diagnostic_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "architecture_decision": {
            "plan": {"path": str(POST_D3_PLAN.relative_to(ROOT)), "sha256": _sha256(POST_D3_PLAN)},
            "section": "21",
            "note": (
                "the first post-D4.4 one-factor candidate is the native Field Integral "
                "formulation; this registration is not FI correctness evidence"
            ),
        },
        "inputs": {
            "work_f_manifest": {"path": str(WORK_F_MANIFEST.relative_to(ROOT)), "sha256": _sha256(WORK_F_MANIFEST)},
            "catalog": {"path": str(CATALOG.relative_to(ROOT)), "sha256": _sha256(CATALOG)},
            "qualification": {"path": str(QUALIFICATION.relative_to(ROOT)), "sha256": _sha256(QUALIFICATION)},
            "result": {"path": str(RESULT.relative_to(ROOT)), "sha256": _sha256(RESULT)},
            "component_diagnosis_manifest": {
                "path": str(COMPONENT_MANIFEST.relative_to(ROOT)),
                "sha256": _sha256(COMPONENT_MANIFEST),
            },
            "component_audit": {"path": str(COMPONENT_AUDIT.relative_to(ROOT)), "sha256": _sha256(COMPONENT_AUDIT)},
            "geometry_jacobian_manifest": {
                "path": str(JACOBIAN_MANIFEST.relative_to(ROOT)),
                "sha256": _sha256(JACOBIAN_MANIFEST),
            },
            "geometry_jacobian_audit": {
                "path": str(JACOBIAN_AUDIT.relative_to(ROOT)),
                "sha256": _sha256(JACOBIAN_AUDIT),
            },
            "adjoint_option_manifest": {
                "path": str(OPTION_MANIFEST.relative_to(ROOT)),
                "sha256": _sha256(OPTION_MANIFEST),
            },
            "surface_area_evidence": {"path": str(SURFACE_AREA.relative_to(ROOT)), "sha256": _sha256(SURFACE_AREA)},
            "mesh_movement_evidence": {"path": str(MESH_MOVEMENT.relative_to(ROOT)), "sha256": _sha256(MESH_MOVEMENT)},
            "original_adjoint_run": {
                "path": str(ORIGINAL_ADJOINT_RUN.relative_to(ROOT)),
                "sha256": _sha256(ORIGINAL_ADJOINT_RUN),
            },
        },
        "openfoam_image": work_f["openfoam_image"],
        "openfoam_image_id": work_f["openfoam_image_id"],
        "openfoam_source_files": {
            "source_root_in_image": SOURCE_ROOT,
            "sha256": _source_hashes(),
        },
        "treatment": {
            "factor": "sensitivityType",
            "baseline": matches[0],
            "treatment": TREATMENT_SENSITIVITY,
            "location": "system/optimisationDict : optimisation.designVariables",
            "isolation": "exactly one dictionary entry is replaced",
        },
        "budget": BUDGET,
        "original_lineage": {
            "case_dir": str(ORIGINAL_CASE.relative_to(ROOT)),
            "optimisationDict_sha256": _sha256(optimisation_dict),
            "sensitivity_type": "surface",
            "time_dir": LINEAGE_TIME,
            "fields": list(LINEAGE_FIELDS),
            "field_hashes": _lineage_hashes(ORIGINAL_CASE),
            "primal_convergence_marker": "op1 solution converged in",
        },
        "fixed_contract": {
            "primal": "the registered upwind base primal lineage is re-solved unchanged",
            "mesh": "unchanged baseline mesh and morpher basis",
            "objective": {
                "drag": "(1, 0, 0), Aref 0.64, rhoInf 1, UInf 1",
                "downforce": "(0, 0, -1), Aref 0.64, rhoInf 1, UInf 1",
            },
            "parameterization": {
                "shapeType": "volumetricBSplines",
                "control_points": [8, 8, 8],
                "degree": [3, 3, 3],
            },
            "active_var_ids": active,
            "active_var_count": len(active),
            "directions": {
                name: ca.load_json(QUALIFICATION)["direction_hashes"][name] for name in DIRECTIONS
            },
            "epsilon_ladder_m": sorted({float(record["epsilon"]) for record in result["rows"]["drag"]}),
        },
        "gates": {
            "relative_rule": RELATIVE_GATE,
            "sign_agreement": "every row keeps the sign of the FD value",
            "plateau_tolerance": PLATEAU_TOLERANCE,
            "near_zero_relative": NEAR_ZERO_RELATIVE,
            "lineage": "time-500 U/p/phi field hashes match the original lineage",
            "derivative_schema": (
                "the same header columns and the same unique finite active 648 varIDs"
            ),
            "adjoint_convergence": "both adjoints report convergence and the run returns zero",
        },
        "baseline_row_classification": classification,
        "judgment_rule": {
            "candidate_formulation_supported": [
                "every originally failing row is within 5% after the treatment",
                "no originally passing row leaves the 5% gate",
                "sign agreement holds for every row",
                "the epsilon plateau spread stays within the registered tolerance",
                "no row is near-zero or unresolved",
                "the base primal field and response lineage is unchanged",
                "the derivative schema is unchanged",
            ],
            "note": "a pass is only a D5 holdout candidate; it is never a derivative qualification",
        },
        "stop_conditions": [
            "baseline lineage changes",
            "either adjoint fails to converge or the schema gate fails",
            "any originally passing control worsens",
            "any originally failing row remains outside 5%",
            "no combination of factors is attempted; no second treatment is added",
        ],
        "claims_not_supported": [
            "A0 is a source-capability and comparison-contract registration only and contains no FI evidence",
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


def _prepare_fi_case() -> dict:
    FI_ROOT.mkdir(parents=True, exist_ok=True)
    _copy_clean_case(FI_CASE)
    dictionary = FI_CASE / "system" / "optimisationDict"
    original = dictionary.read_text(encoding="utf-8")
    matches = re.findall(SENSITIVITY_PATTERN, original)
    if len(matches) != 1 or matches[0].strip() != BASELINE_SENSITIVITY:
        raise SystemExit("the copied optimisationDict does not declare exactly one surface sensitivity")
    treated = re.sub(SENSITIVITY_PATTERN, TREATMENT_SENSITIVITY, original, count=1)
    dictionary.write_text(treated, encoding="utf-8", newline="\n")
    original_lines = set(original.splitlines())
    treated_lines = set(treated.splitlines())
    changed = sorted(treated_lines - original_lines)
    removed = sorted(original_lines - treated_lines)
    isolation = bool(
        len(changed) == 1
        and changed[0].strip() == TREATMENT_SENSITIVITY
        and len(removed) == 1
        and removed[0].strip() == BASELINE_SENSITIVITY
    )
    if not isolation:
        raise SystemExit("the FI treatment is not an isolated single-line change")
    return {"changed_lines": changed, "removed_lines": removed, "isolated": isolation}


def run() -> dict:
    if EVIDENCE.exists():
        raise SystemExit("FI formulation diagnostic evidence already exists; refuse overwrite")
    manifest = ca.load_json(MANIFEST)
    _verify_inputs(manifest)
    work_f = ca.load_json(WORK_F_MANIFEST)
    qualification = ca.load_json(QUALIFICATION)
    active = tuple(int(value) for value in manifest["fixed_contract"]["active_var_ids"])
    directions = {
        name: np.asarray(entry["values"], dtype=np.float64)
        for name, entry in qualification["directions"].items()
    }
    edit = _prepare_fi_case()
    run_result = run_openfoam_case(
        FI_CASE,
        backend="docker",
        dry_run=False,
        timeout_seconds=int(work_f["solver_budget"]["solver_timeout_seconds"]),
        docker_image=work_f["openfoam_image"],
    )
    log_path = FI_CASE / "log.adjointOptimisationFoam"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    sensitivity_selection = re.findall(r"adjointSensitivity type\s*:\s*(\S+)", log)
    targets = {name: f"{name} solution converged in" in log for name in ("adjDownforce", "adjDrag")}
    convergence = {
        **targets,
        "returncode": getattr(run_result, "returncode", None),
        "sensitivity_selected": sensitivity_selection[-1] if sensitivity_selection else None,
    }
    if convergence["returncode"] != 0 or not all(targets.values()):
        raise SystemExit("the FI adjoint run did not converge; capability failure, no verdict")
    if convergence["sensitivity_selected"] != "shapeFI":
        raise SystemExit("the run did not select the shapeFI sensitivity; no verdict")

    derivative_paths = sorted((FI_CASE / "optimisation" / "derivatives").glob("*"))
    tables: dict[str, object] = {}
    for response, solver in (("downforce", "adjDownforce"), ("drag", "adjDrag")):
        matches = [path for path in derivative_paths if solver in path.name]
        if len(matches) != 1:
            raise SystemExit(f"the FI run did not write exactly one {solver} derivative file")
        tables[response] = parse_derivative_table(matches[0], expected_solver=solver)
    schema = {}
    ordered: dict[str, dict] = {}
    for response, table in tables.items():
        ids = table.var_ids
        schema[response] = {
            "rows": len(ids),
            "unique": len(set(ids)) == len(ids),
            "matches_active_set": set(ids) == set(active),
            "finite": True,
        }
        if not (schema[response]["unique"] and schema[response]["matches_active_set"]):
            raise SystemExit(f"FI derivative schema failed for {response}")
        ordered[response] = order_columns(table, active)

    lineage = _lineage_check(manifest, FI_CASE, log)
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
            "fi_analytic": contracted["total"],
            "baseline_ratio": baseline["ratio"],
            "fi_ratio": ratio,
            "baseline_within_gate": baseline["within_gate"],
            "fi_within_gate": bool(within),
            "sign_agreement": bool(sign),
            "near_zero": bool(abs(contracted["total"]) <= baseline["noise_floor"]),
            "components": {name: contracted[name] for name in COMPONENT_COLUMNS + ("total",)},
            "closure": component_closure(contracted),
        }
    plateau: dict[str, dict] = {}
    plateau_pass = True
    for response in ("downforce", "drag"):
        for direction in DIRECTIONS:
            ratios = [
                float(row["fi_ratio"])
                for row in rows.values()
                if row["response"] == response
                and row["direction"] == direction
                and row["fi_ratio"] is not None
            ]
            spread = (max(ratios) - min(ratios)) if len(ratios) > 1 else None
            passed = bool(spread is not None and spread <= PLATEAU_TOLERANCE)
            plateau[f"{response}__{direction}"] = {
                "ratios": ratios,
                "spread": spread,
                "tolerance": PLATEAU_TOLERANCE,
                "pass": passed,
            }
            plateau_pass = plateau_pass and passed

    failing = [row for row in rows.values() if not row["baseline_within_gate"]]
    passing = [row for row in rows.values() if row["baseline_within_gate"]]
    judgment = {
        "original_failing_rows_all_within": bool(
            failing and all(row["fi_within_gate"] for row in failing)
        ),
        "original_passing_rows_none_worsened": bool(
            all(row["fi_within_gate"] for row in passing)
        ),
        "sign_agreement_all": bool(all(row["sign_agreement"] for row in rows.values())),
        "plateau_all": plateau_pass,
        "no_near_zero_artifacts": bool(not any(row["near_zero"] for row in rows.values())),
        "lineage_unchanged": bool(lineage["all_field_hashes_match"] and lineage["primal_converged"]),
        "schema_unchanged": bool(
            all(entry["unique"] and entry["matches_active_set"] and entry["finite"] for entry in schema.values())
        ),
        "n_baseline_failing": len(failing),
        "n_baseline_passing": len(passing),
    }
    judgment["candidate_formulation_supported"] = bool(
        judgment["original_failing_rows_all_within"]
        and judgment["original_passing_rows_none_worsened"]
        and judgment["sign_agreement_all"]
        and judgment["plateau_all"]
        and judgment["no_near_zero_artifacts"]
        and judgment["lineage_unchanged"]
        and judgment["schema_unchanged"]
    )
    evidence = {
        "kind": "stage_s_work_f_fi_formulation_diagnostic",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "treatment": {
            "factor": "sensitivityType",
            "baseline": "surface",
            "treatment": "shapeFI",
            "diagnostic_only": True,
        },
        "case_dir": str(FI_CASE.relative_to(ROOT)),
        "scheme_edit": edit,
        "openfoam_run": {
            "returncode": getattr(run_result, "returncode", None),
            "timed_out": getattr(run_result, "timed_out", None),
        },
        "convergence": convergence,
        "schema": schema,
        "derivative_files": {
            response: {"name": Path(table.path).name, "sha256": table.sha256}
            for response, table in tables.items()
        },
        "lineage": lineage,
        "rows": rows,
        "plateau": plateau,
        "judgment": judgment,
        "summary": {
            "candidate_formulation_supported": judgment["candidate_formulation_supported"],
            "next": (
                "D5 independent holdout (6 primals) candidate"
                if judgment["candidate_formulation_supported"]
                else "register the 0-run architecture memo (plan section 21.6)"
            ),
            "derivative_qualified": False,
            "shape_update_allowed": False,
            "original_verdict_unchanged": True,
        },
        "claims_supported": [
            "one isolated native FI sensitivity treatment was run and judged against the pre-registered conditions",
        ],
        "claims_not_supported": [
            "a pass is only a D5 holdout candidate; this diagnostic does not qualify the derivative",
            "the FI treatment is not a production setting",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    print(json.dumps(judgment, indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F post-D4.4 A0/A1")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.run:
        run()
    else:
        parser.error("specify --register or --run")


if __name__ == "__main__":
    main()
