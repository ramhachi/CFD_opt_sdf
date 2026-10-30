"""Work F post-D3 diagnosis D4.0 and D4.1.

``--register`` fixes the D4.0 diagnostic manifest before any D4 computation:
the input evidence hashes, the four registered directions, the upwind and
linearUpwind derivative-file hashes, the OpenFOAM image identity and the v2512
source hashes behind the component semantics, the component summation formula,
the ablation order, the sole-cause rule and the holdout-seed rule.

``--run`` executes the solver-free D4.1 derivative-component audit: every
derivative column is contracted with every registered direction, and the
component closure, cancellation index, FD residual and component-level
explanation hypotheses are recorded. No primal or adjoint solver is started
and no registered verdict or threshold is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.stage_s_adjoint_qualification import active_var_ids  # noqa: E402
from cfd_sdf.stage_s_component_diagnosis import (  # noqa: E402
    AUXILIARY_COLUMNS,
    CLOSURE_ABSOLUTE_TOLERANCE,
    COMPONENT_COLUMNS,
    DERIVATIVE_SUM_FORMULA,
    cancellation_index,
    component_closure,
    contract_columns,
    drop_component_hypothesis,
    holdout_seed,
    order_columns,
    parse_derivative_table,
    relative_gate,
    single_scalar_hypothesis,
)

POST_D3_PLAN = ROOT / "docs/stage_s_work_f_post_d3_plan_2026_09_25.md"
FD_DIAGNOSIS_PLAN = ROOT / "docs/stage_s_work_f_fd_diagnosis_plan_2026_09_25.md"
WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"
PERTURBATION_SIDES = ROOT / "docs/evidence/stage_s_work_f_perturbation_sides_2026_09.json"
D1_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_realized_direction_audit_manifest_2026_09.json"
D1_ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_realized_direction_audit_2026_09.json"
D2_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_sensitivity_semantics_audit_manifest_2026_09.json"
D2_ARTIFACT = ROOT / "docs/evidence/stage_s_work_f_sensitivity_semantics_audit_2026_09.json"
D3_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_manifest_2026_09.json"
D3_PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_preflight_2026_09.json"
D3_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_2026_09.json"
D3_PRESERVED = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_ratio_error_2026_09.json"
UPWIND_DERIVATIVES = ROOT / "work/stage_s_work_f_v1/adjoint/base/optimisation/derivatives"
LINEAR_DERIVATIVES = (
    ROOT / "work/stage_s_work_f_v1/discretization_linearUpwind/adjoint/base/optimisation/derivatives"
)
MANIFEST = ROOT / "docs/evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json"
AUDIT = ROOT / "docs/evidence/stage_s_work_f_derivative_component_audit_2026_09.json"

UPWIND_DIRECTIONS = (
    "downforce_gradient_aligned",
    "drag_gradient_aligned",
    "random_seed_11",
    "random_seed_2026",
)
LINEAR_DIRECTIONS = ("downforce_gradient_aligned", "random_seed_11", "random_seed_2026")
LINEAR_EPSILON = 5.0e-4
SOLE_CAUSE_RULE = {
    "relative_gate": 0.05,
    "requirements": [
        "original failing rows all move within 5% of one",
        "no original passing control leaves the 5% gate",
        "sign agreement holds for every direction",
        "response identity and derivative schema are unchanged",
        "base primal field/response lineage is unchanged",
        "no apparent pass from a near-zero/cancellation artifact",
    ],
}
ABLATION_ORDER = (
    {
        "order": 1,
        "option": "includeSurfaceArea",
        "baseline": "true",
        "treatment": "false",
        "fixed": {
            "includeMeshMovement": "true",
            "sensitivityType": "surface",
            "smoothSensitivities": "false",
            "shapeType": "volumetricBSplines",
        },
        "rationale": "measure the surface-area term contribution; treatment is diagnostic only",
    },
    {
        "order": 2,
        "option": "includeMeshMovement",
        "baseline": "true",
        "treatment": "false",
        "fixed": {
            "includeSurfaceArea": "as decided by the first ablation",
            "sensitivityType": "surface",
            "smoothSensitivities": "false",
            "shapeType": "volumetricBSplines",
        },
        "rationale": "runs only if the first ablation is not a sole cause; diagnostic only",
    },
)
SOURCE_FILES = (
    "src/optimisation/adjointOptimisation/adjoint/parameterization/NURBS/NURBS3DVolume/"
    "NURBS3DVolume/NURBS3DVolume.C",
    "src/optimisation/adjointOptimisation/adjoint/parameterization/NURBS/NURBS3DVolume/"
    "NURBS3DVolume/NURBS3DVolume.H",
    "src/optimisation/adjointOptimisation/adjoint/parameterization/NURBS/NURBS3DVolume/"
    "volBSplinesBase/volBSplinesBase.C",
    "src/optimisation/adjointOptimisation/adjoint/parameterization/NURBS/NURBS3DVolume/"
    "volBSplinesBase/volBSplinesBase.H",
    "src/optimisation/adjointOptimisation/adjoint/optimisation/designVariables/shape/"
    "volumetricBSplines/volumetricBSplinesDesignVariables.C",
    "src/optimisation/adjointOptimisation/adjoint/optimisation/designVariables/shape/"
    "volumetricBSplines/volumetricBSplinesDesignVariables.H",
    "src/optimisation/adjointOptimisation/adjoint/optimisation/designVariables/shape/"
    "shapeDesignVariables/shapeDesignVariables.C",
    "src/optimisation/adjointOptimisation/adjoint/optimisation/designVariables/shape/"
    "shapeDesignVariables/shapeDesignVariables.H",
    "src/optimisation/adjointOptimisation/adjoint/optimisation/adjointSensitivity/"
    "adjointSensitivity/shape/surfacePoints/sensitivitySurfacePoints.C",
    "src/optimisation/adjointOptimisation/adjoint/optimisation/adjointSensitivity/"
    "adjointSensitivity/shape/surfacePoints/sensitivitySurfacePoints.H",
)
SOURCE_ROOT = "/usr/lib/openfoam/openfoam2512"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _input_records() -> dict[str, dict[str, str]]:
    files = {
        "post_d3_plan": POST_D3_PLAN,
        "fd_diagnosis_plan": FD_DIAGNOSIS_PLAN,
        "work_f_manifest": WORK_F_MANIFEST,
        "catalog": CATALOG,
        "qualification": QUALIFICATION,
        "result": RESULT,
        "perturbation_sides": PERTURBATION_SIDES,
        "d1_manifest": D1_MANIFEST,
        "d1_artifact": D1_ARTIFACT,
        "d2_manifest": D2_MANIFEST,
        "d2_artifact": D2_ARTIFACT,
        "d3_manifest": D3_MANIFEST,
        "d3_preflight": D3_PREFLIGHT,
        "d3_evidence": D3_EVIDENCE,
        "d3_preserved_ratio_error": D3_PRESERVED,
    }
    return {
        name: {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
        for name, path in files.items()
    }


def _derivative_files(directory: Path) -> dict[str, dict]:
    paths = sorted(directory.glob("*"))
    records: dict[str, dict] = {}
    for response, solver in (("downforce", "adjDownforce"), ("drag", "adjDrag")):
        table = parse_derivative_table(
            next(path for path in paths if solver in path.name), expected_solver=solver
        )
        path = Path(table.path)
        records[response] = {
            "path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
            "sha256": table.sha256,
            "solver": table.solver,
            "final_iteration": table.final_iteration,
            "rows": len(table.var_ids),
        }
    return records


def _image_id(image: str) -> str:
    return subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _source_hashes(image: str) -> dict[str, str]:
    command = " && ".join(f"sha256sum {SOURCE_ROOT}/{path}" for path in SOURCE_FILES)
    completed = subprocess.run(
        ["docker", "run", "--rm", image, "bash", "-lc", command],
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
        raise SystemExit("not every registered source file was hashed inside the image")
    return records


def _direction_records(qualification: dict) -> dict[str, dict]:
    active = [int(value) for value in qualification["derivative_contract"]["active_var_ids"]]
    records: dict[str, dict] = {}
    for name, entry in qualification["directions"].items():
        values = np.asarray(entry["values"], dtype=np.float64)
        if values.size != len(active):
            raise SystemExit(f"direction {name} does not match the active variable count")
        array_sha = hashlib.sha256(
            np.ascontiguousarray(values, dtype=np.float64).tobytes()
        ).hexdigest()
        if array_sha != qualification["direction_hashes"][name]:
            raise SystemExit(f"direction {name} hash does not reproduce")
        records[name] = {
            "sha256": array_sha,
            "unit_inf_norm": float(np.max(np.abs(values))),
            "l2_norm": float(np.linalg.norm(values)),
            "role": entry["kind"],
            "seed": entry.get("seed"),
        }
    return records


def register() -> dict:
    if MANIFEST.exists():
        raise SystemExit("component diagnosis manifest already exists; refuse overwrite")
    qualification = ca.load_json(QUALIFICATION)
    result = ca.load_json(RESULT)
    work_f = ca.load_json(WORK_F_MANIFEST)
    catalog = ca.load_json(CATALOG)
    images = {result.get("openfoam_image"), work_f.get("openfoam_image")}
    if len(images) != 1 or None in images:
        raise SystemExit("the registered evidence disagrees on the OpenFOAM image")
    image = images.pop()
    image_id = _image_id(image)
    if result.get("openfoam_image_id") != image_id:
        raise SystemExit("the registered OpenFOAM image id does not match the local image")
    ladder = [float(value) for value in catalog["shared_catalog"]["epsilons_m"]]
    sorted_ladder = sorted(ladder)
    holdout_epsilon = sorted_ladder[len(sorted_ladder) // 2]
    manifest = {
        "kind": "stage_s_work_f_component_diagnosis_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "post_d3_plan": {
            "path": str(POST_D3_PLAN.relative_to(ROOT)),
            "sha256": _sha256(POST_D3_PLAN),
        },
        "inputs": _input_records(),
        "derivative_files": {
            "upwind": _derivative_files(UPWIND_DERIVATIVES),
            "linearUpwind": _derivative_files(LINEAR_DERIVATIVES),
        },
        "directions": _direction_records(qualification),
        "openfoam_image": image,
        "openfoam_image_id": image_id,
        "openfoam_source_files": {
            "source_root_in_image": SOURCE_ROOT,
            "sha256": _source_hashes(image),
        },
        "component_formula": {
            "total": DERIVATIVE_SUM_FORMULA,
            "components": list(COMPONENT_COLUMNS),
            "auxiliary": list(AUXILIARY_COLUMNS),
            "closure_absolute_tolerance": CLOSURE_ABSOLUTE_TOLERANCE,
        },
        "audit_scope": {
            "upwind": {
                "directions": list(UPWIND_DIRECTIONS),
                "epsilons_m": ladder,
                "fd_source": "registered surface-FD result rows",
            },
            "linearUpwind": {
                "directions": list(LINEAR_DIRECTIONS),
                "epsilons_m": [LINEAR_EPSILON],
                "fd_source": "registered D3 perturbation side means",
            },
        },
        "ablations": list(ABLATION_ORDER),
        "sole_cause_rule": SOLE_CAUSE_RULE,
        "holdout_rule": {
            "seed_derivation": (
                "seed_i = first 8 bytes (big-endian) of "
                "sha256(manifest_sha256 + ':holdout:seed:' + i), i >= 1"
            ),
            "n_random_directions_min": 2,
            "control_direction": "downforce_gradient_aligned",
            "normalization": "unit infinity norm over the active variables",
            "epsilon_m": holdout_epsilon,
            "epsilon_rule": "upper central value of the registered epsilon ladder",
            "sides": "plus and minus",
            "minimum_primals": 6,
        },
        "forbidden": [
            "adding an ablation factor after seeing the D4 results",
            "changing more than one option per ablation",
            "fitting a component scale as a production correction",
            "calling D4 a derivative qualification",
        ],
        "stop_conditions": [
            "a failed closure gate stops the component audit",
            "no registered epsilon, direction, threshold or verdict is changed",
            "this diagnosis never authorizes a shape update",
        ],
        "claims_not_supported": [
            "this registration is not a derivative qualification and produces no CFD evidence",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)}, indent=2))
    return manifest


def _verify_inputs(manifest: dict) -> None:
    for name, record in manifest["inputs"].items():
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"registered input changed: {name}")
    for scheme, responses in manifest["derivative_files"].items():
        for response, record in responses.items():
            if _sha256(ROOT / record["path"]) != record["sha256"]:
                raise SystemExit(f"registered {scheme} derivative file changed: {response}")


def _response_scales(catalog: dict) -> dict[str, float]:
    scales: dict[str, float] = {}
    for response, record in catalog["manifests"].items():
        fixture = ca.load_json(ROOT / record["path"])["manifest"]["fixture"]
        scales[response] = float(fixture["response_scale"])
    return scales


def _upwind_rows(
    *,
    manifest: dict,
    qualification: dict,
    result: dict,
    scales: dict[str, float],
) -> tuple[list[dict], float]:
    active = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    directions = {
        name: np.asarray(entry["values"], dtype=np.float64)
        for name, entry in qualification["directions"].items()
    }
    tables = {}
    for response, record in manifest["derivative_files"]["upwind"].items():
        solver = "adjDownforce" if response == "downforce" else "adjDrag"
        tables[response] = parse_derivative_table(
            ROOT / record["path"], expected_solver=solver
        )
        if tables[response].sha256 != record["sha256"]:
            raise SystemExit(f"upwind derivative hash changed: {response}")
    ordered = {response: order_columns(table, active) for response, table in tables.items()}
    rows: list[dict] = []
    max_deviation = 0.0
    for response, response_rows in result["rows"].items():
        floor = 1.0e-3 * abs(scales[response])
        for record in response_rows:
            name = record["direction"]
            epsilon = float(record["epsilon"])
            contracted = contract_columns(ordered[response], directions[name])
            registered = float(record["analytic"])
            max_deviation = max(max_deviation, abs(contracted["total"] - registered))
            fd = float(record["fd"])
            ratio, within, sign = relative_gate(contracted["total"], fd)
            row = {
                "row_id": f"upwind__{response}__{name}__{epsilon:g}",
                "scheme": "upwind",
                "response": response,
                "direction": name,
                "epsilon": epsilon,
                "fd": fd,
                "fd_source": "registered surface-FD result row",
                "registered_analytic": registered,
                "analytic_registered_deviation": contracted["total"] - registered,
                "d_total": contracted["total"],
                **{f"d_{key}": contracted[key] for key in COMPONENT_COLUMNS + AUXILIARY_COLUMNS},
                "noise_floor": floor,
                "component_sum": float(sum(contracted[key] for key in COMPONENT_COLUMNS)),
                "closure": component_closure(contracted),
                "cancellation_index": cancellation_index(contracted, floor=floor),
                "fd_residual": fd - contracted["total"],
                "ratio": ratio,
                "relative_error": abs(ratio - 1.0) if ratio is not None else None,
                "within_gate": bool(within),
                "sign_agreement": bool(sign),
                "near_zero_analytic": bool(abs(contracted["total"]) <= floor),
            }
            rows.append(row)
    return rows, max_deviation


def _linear_rows(
    *,
    manifest: dict,
    qualification: dict,
    d3: dict,
    scales: dict[str, float],
) -> tuple[list[dict], float]:
    active = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    directions = {
        name: np.asarray(entry["values"], dtype=np.float64)
        for name, entry in qualification["directions"].items()
    }
    tables = {}
    for response, record in manifest["derivative_files"]["linearUpwind"].items():
        solver = "adjDownforce" if response == "downforce" else "adjDrag"
        tables[response] = parse_derivative_table(
            ROOT / record["path"], expected_solver=solver
        )
        if tables[response].sha256 != record["sha256"]:
            raise SystemExit(f"linearUpwind derivative hash changed: {response}")
    ordered = {response: order_columns(table, active) for response, table in tables.items()}
    rows: list[dict] = []
    max_comparison_deviation = 0.0
    for response in ("downforce", "drag"):
        response_key = "Cd" if response == "drag" else "downforce"
        floor = 1.0e-3 * abs(scales[response])
        for name in LINEAR_DIRECTIONS:
            plus = d3["sides"][f"{name}__plus"]
            minus = d3["sides"][f"{name}__minus"]
            if not (plus["pass"] and minus["pass"]):
                raise SystemExit(f"linearUpwind side gate failed: {response}/{name}")
            fd = (float(plus[response_key]) - float(minus[response_key])) / (2.0 * LINEAR_EPSILON)
            contracted = contract_columns(ordered[response], directions[name])
            comparison = d3["diagnostic"][f"{response}__{name}"]
            max_comparison_deviation = max(
                max_comparison_deviation,
                abs(contracted["total"] - float(comparison["analytic_linearUpwind"])),
            )
            ratio, within, sign = relative_gate(contracted["total"], fd)
            rows.append(
                {
                    "row_id": f"linearUpwind__{response}__{name}__{LINEAR_EPSILON:g}",
                    "scheme": "linearUpwind",
                    "response": response,
                    "direction": name,
                    "epsilon": LINEAR_EPSILON,
                    "fd": fd,
                    "fd_source": "registered D3 perturbation side means",
                    "registered_analytic": float(comparison["analytic_linearUpwind"]),
                    "analytic_registered_deviation": contracted["total"]
                    - float(comparison["analytic_linearUpwind"]),
                    "d_total": contracted["total"],
                    **{f"d_{key}": contracted[key] for key in COMPONENT_COLUMNS + AUXILIARY_COLUMNS},
                    "noise_floor": floor,
                    "component_sum": float(sum(contracted[key] for key in COMPONENT_COLUMNS)),
                    "closure": component_closure(contracted),
                    "cancellation_index": cancellation_index(contracted, floor=floor),
                    "fd_residual": fd - contracted["total"],
                    "ratio": ratio,
                    "relative_error": abs(ratio - 1.0) if ratio is not None else None,
                    "within_gate": bool(within),
                    "sign_agreement": bool(sign),
                    "near_zero_analytic": bool(abs(contracted["total"]) <= floor),
                }
            )
    return rows, max_comparison_deviation


def _scheme_shift(upwind_rows: list[dict], linear_rows: list[dict]) -> dict[str, dict]:
    upwind_index = {
        (row["response"], row["direction"], row["epsilon"]): row for row in upwind_rows
    }
    shift: dict[str, dict] = {}
    for row in linear_rows:
        key = (row["response"], row["direction"], row["epsilon"])
        baseline = upwind_index[key]
        shift[f"{row['response']}__{row['direction']}__{row['epsilon']:g}"] = {
            "components": {
                name: {
                    "upwind": baseline[f"d_{name}"],
                    "linearUpwind": row[f"d_{name}"],
                    "delta": row[f"d_{name}"] - baseline[f"d_{name}"],
                }
                for name in COMPONENT_COLUMNS
            },
            "total": {
                "upwind": baseline["d_total"],
                "linearUpwind": row["d_total"],
                "delta": row["d_total"] - baseline["d_total"],
            },
        }
    return shift


def _scheme_explanations(rows: list[dict]) -> dict:
    return {
        "drop_one_component": [
            drop_component_hypothesis(rows, component) for component in COMPONENT_COLUMNS
        ],
        "single_scalar": single_scalar_hypothesis(rows),
    }


def run() -> dict:
    if AUDIT.exists():
        raise SystemExit("component audit evidence already exists; refuse overwrite")
    manifest = ca.load_json(MANIFEST)
    _verify_inputs(manifest)
    qualification = ca.load_json(QUALIFICATION)
    result = ca.load_json(RESULT)
    catalog = ca.load_json(CATALOG)
    d3 = ca.load_json(D3_EVIDENCE)
    scales = _response_scales(catalog)

    upwind_rows, upwind_deviation = _upwind_rows(
        manifest=manifest, qualification=qualification, result=result, scales=scales
    )
    linear_rows, linear_deviation = _linear_rows(
        manifest=manifest, qualification=qualification, d3=d3, scales=scales
    )
    upwind_explanations = _scheme_explanations(upwind_rows)
    linear_explanations = _scheme_explanations(linear_rows)
    closure_max = max(abs(row["closure"]) for row in (*upwind_rows, *linear_rows))
    closure_ok = bool(closure_max <= CLOSURE_ABSOLUTE_TOLERANCE)
    if not closure_ok:
        raise SystemExit(f"component closure failed: max {closure_max:g}")
    evidence = {
        "kind": "stage_s_work_f_derivative_component_audit",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "component_formula": manifest["component_formula"],
        "rows": upwind_rows + linear_rows,
        "scheme_component_shift": _scheme_shift(upwind_rows, linear_rows),
        "explanations": {
            "upwind": upwind_explanations,
            "linearUpwind": linear_explanations,
        },
        "checks": {
            "closure_within_tolerance": closure_ok,
            "max_abs_closure": closure_max,
            "upwind_registered_analytic_max_deviation": upwind_deviation,
            "linearUpwind_registered_analytic_max_deviation": linear_deviation,
            "n_upwind_rows": len(upwind_rows),
            "n_linearUpwind_rows": len(linear_rows),
        },
        "summary": {
            "component_closure_ok": closure_ok,
            "single_component_drop_explains_upwind": any(
                entry["explains_all_directions"]
                for entry in upwind_explanations["drop_one_component"]
            ),
            "single_component_drop_explains_linearUpwind": any(
                entry["explains_all_directions"]
                for entry in linear_explanations["drop_one_component"]
            ),
            "single_scalar_explains_upwind": upwind_explanations["single_scalar"][
                "explains_all_directions"
            ],
            "single_scalar_explains_linearUpwind": linear_explanations["single_scalar"][
                "explains_all_directions"
            ],
            "derivative_qualified": False,
            "shape_update_allowed": False,
            "original_verdict_unchanged": True,
        },
        "claims_supported": [
            "every registered derivative column was contracted per direction and the component closure was recorded",
        ],
        "claims_not_supported": [
            "this solver-free audit does not qualify the derivative or authorize a shape update",
            "post-hoc component drops and fitted scales are explanatory only",
        ],
    }
    AUDIT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": evidence["summary"],
                "checks": evidence["checks"],
                "upwind_drop_one": {
                    entry["dropped_component"]: {
                        "pass": entry["n_passing_after_drop"],
                        "rows": entry["n_rows"],
                        "worsened": entry["n_worsened_controls"],
                        "explains": entry["explains_all_directions"],
                    }
                    for entry in upwind_explanations["drop_one_component"]
                },
                "linearUpwind_drop_one": {
                    entry["dropped_component"]: {
                        "pass": entry["n_passing_after_drop"],
                        "rows": entry["n_rows"],
                        "worsened": entry["n_worsened_controls"],
                        "explains": entry["explains_all_directions"],
                    }
                    for entry in linear_explanations["drop_one_component"]
                },
            },
            indent=2,
        )
    )
    return evidence


def _holdout_preview() -> None:
    manifest_sha = _sha256(MANIFEST)
    print(json.dumps({"manifest_sha256": manifest_sha, "seeds": [holdout_seed(manifest_sha, 1), holdout_seed(manifest_sha, 2)]}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F post-D3 diagnosis D4.0/D4.1")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--holdout-preview", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.run:
        run()
    elif args.holdout_preview:
        _holdout_preview()
    else:
        parser.error("specify --register, --run or --holdout-preview")


if __name__ == "__main__":
    main()
