"""Work F bounded discretization diagnostic (diagnosis D3).

Registers a single-factor manifest (primal convection scheme
``bounded Gauss upwind`` -> ``bounded Gauss linearUpwind grad(U)``), builds an
independent base/adjoint lineage, runs the base primal and both adjoints, and
runs six perturbation primals (three registered directions at one registered
middle epsilon) to test whether the direction-dependent analytic-vs-FD
mismatch moves toward one under a second-order primal discretization. The
original verdict and thresholds are never modified.
"""

from __future__ import annotations

import argparse
import hashlib
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
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1, write_stage_v_qualification  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.fixed_grid_contract import CartesianCellGrid  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.stage_s_adjoint_case import (  # noqa: E402
    ADJOINT_SOLVER_NAMES,
    AdjointObjective,
    AdjointPatchRoles,
    build_dynamic_mesh_dict,
    render_adjoint_case,
    verify_adjoint_case,
)
from cfd_sdf.stage_s_adjoint_qualification import (  # noqa: E402
    active_var_ids,
    parse_derivative_file,
    response_derivative_vector,
)
from cfd_sdf.stage_s_perturbation import (  # noqa: E402
    build_control_point_movement,
    extract_patch_surface,
    fixed_patch_immobility,
    movement_to_text,
    parse_check_mesh_qualified,
    surface_geometry_checks,
)
from stage_t_filtered_ramp import SOLVE_ONLY_ALLRUN  # noqa: E402

WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
RESULT = ROOT / "docs/evidence/stage_s_work_f_surface_fd_result_2026_09.json"
BASELINE_CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"
MORPHER = ROOT / "work/stage_s_work_f_v1/tools/moveControlPoints"
SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
D3_ROOT = ROOT / "work/stage_s_work_f_v1/discretization_linearUpwind"
D3_BASE = D3_ROOT / "base"
D3_ADJOINT = D3_ROOT / "adjoint/base"
D3_PERTURBATIONS = D3_ROOT / "perturbations"
MANIFEST = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_manifest_2026_09.json"
PREFLIGHT = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_preflight_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_2026_09.json"
PRESERVED = ROOT / "docs/evidence/stage_s_work_f_discretization_diagnostic_ratio_error_2026_09.json"
BASELINE_SCHEME_PATTERN = r"div\(phi,U\)\s+[^;]+;"
BASELINE_SCHEME = "div(phi,U) bounded Gauss upwind;"
TREATMENT_SCHEME = "div(phi,U) bounded Gauss linearUpwind grad(U);"
EPSILON = 5.0e-4
DIRECTIONS = ("downforce_gradient_aligned", "random_seed_11", "random_seed_2026")
OBJECTIVE_SIGNS = {"drag": 1.0, "downforce": 1.0}
ADJOINT_ALLRUN = "#!/usr/bin/env bash\nset -eo pipefail\nadjointOptimisationFoam | tee log.adjointOptimisationFoam\n"


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _inputs() -> dict[str, dict[str, str]]:
    files = {
        "work_f_manifest": WORK_F_MANIFEST,
        "catalog": CATALOG,
        "qualification": QUALIFICATION,
        "result": RESULT,
    }
    return {name: {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)} for name, path in files.items()}


def register() -> dict:
    if MANIFEST.exists():
        raise SystemExit("discretization diagnostic manifest already exists")
    manifest = {
        "kind": "stage_s_work_f_discretization_diagnostic_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "hypothesis": (
            "the first-order upwind primal discretization behind the continuous adjoint "
            "carries direction-dependent error; a second-order primal scheme moves the "
            "failing ratio toward one without degrading the controls"
        ),
        "factor": {"name": "div(phi,U)", "baseline": BASELINE_SCHEME.strip(), "treatment": TREATMENT_SCHEME.strip()},
        "epsilon_m": EPSILON,
        "directions": list(DIRECTIONS),
        "diagnostic_only": True,
        "gates": {
            "base_primal": "registered residualControl and force-stationarity profile",
            "adjoint": "both adjoint solvers converge and write their derivative files",
            "sides": "six perturbation sides pass geometry, clearance, checkMesh and primal gates",
            "isolation": "only the primal div(phi,U) scheme differs from the original lineage",
        },
        "inputs": _inputs(),
        "stop_conditions": [
            "a failed base or adjoint gate stops the diagnostic; the scheme is not adopted",
            "one result never qualifies the derivative or authorizes a shape update",
            "no epsilon, direction or tolerance change after the result",
        ],
        "claims_not_supported": [
            "this bounded diagnostic does not qualify the surface derivative",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)}, indent=2))
    return manifest


def _objectives(catalog: dict, metadata: dict) -> tuple[AdjointObjective, ...]:
    reference = metadata["force_reference"]
    free_patch = catalog["shared_catalog"]["fixed_regions"]["free_patch"]
    objectives = []
    for response in ("drag", "downforce"):
        identity = json.loads(
            (ROOT / catalog["manifests"][response]["path"]).read_text(encoding="utf-8")
        )["manifest"]["fixture"]["response_identity"]
        objectives.append(
            AdjointObjective(
                response=response,
                solver_name=ADJOINT_SOLVER_NAMES[response],
                direction=tuple(float(value) for value in identity["direction"]),
                patches=(free_patch,),
                area_m2=float(reference["area_m2"]),
                rho_inf=float(reference["density_kg_m3"]),
                u_inf=float(reference["freestream_speed_mps"]),
            )
        )
    return tuple(objectives)


def preflight() -> dict:
    if PREFLIGHT.exists():
        raise SystemExit("discretization diagnostic preflight already exists")
    manifest = ca.load_json(MANIFEST)
    for name, record in manifest["inputs"].items():
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"diagnostic input changed: {name}")
    catalog = ca.load_json(CATALOG)
    if D3_ROOT.exists():
        shutil.rmtree(D3_ROOT)
    shutil.copytree(BASELINE_CASE, D3_BASE)
    for relative in ("postProcessing", "log.simpleFoam", "stage_v_qualification.json"):
        path = D3_BASE / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
    for child in list(D3_BASE.iterdir()):
        if child.is_dir() and child.name not in {"0", "constant", "system"}:
            shutil.rmtree(child)
    schemes = D3_BASE / "system" / "fvSchemes"
    original = schemes.read_text(encoding="utf-8")
    pattern = re.compile(BASELINE_SCHEME_PATTERN)
    matches = pattern.findall(original)
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one div(phi,U) scheme entry, found {len(matches)}")
    treated = pattern.sub(TREATMENT_SCHEME, original, count=1)
    schemes.write_text(treated, encoding="utf-8", newline="\n")
    metadata = ca.load_json(D3_BASE / "case_metadata.json")
    objectives = _objectives(catalog, metadata)
    patch_roles = AdjointPatchRoles(
        inflow=("inlet",),
        outflow=("outlet",),
        symmetry=("sideMin", "sideMax", "top"),
        walls=("bottom",),
        design=catalog["shared_catalog"]["fixed_regions"]["free_patch"],
    )
    basis = catalog["shared_catalog"]["surface_basis"]
    render_adjoint_case(
        source_case=D3_BASE,
        target_case=D3_ADJOINT,
        objectives=objectives,
        patch_roles=patch_roles,
        box_min=tuple(float(value) for value in basis["box_m"]["min"]),
        box_max=tuple(float(value) for value in basis["box_m"]["max"]),
        n_cps=tuple(int(value) for value in basis["control_points"]),
        degree=(3, 3, 3),
        primal_iterations=3000,
        primal_residual=1.0e-6,
        adjoint_iterations=3000,
        adjoint_residual=1.0e-6,
    )
    structural = verify_adjoint_case(D3_ADJOINT, objectives=objectives, patch_roles=patch_roles)
    original_lines = set(original.splitlines())
    treated_lines = set(treated.splitlines())
    changed_lines = sorted(treated_lines - original_lines)
    removed_lines = sorted(original_lines - treated_lines)
    artifact = {
        "kind": "stage_s_work_f_discretization_diagnostic_preflight",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "scheme": {
            "baseline": BASELINE_SCHEME.strip(),
            "treatment": TREATMENT_SCHEME.strip(),
            "changed_lines": changed_lines,
            "removed_lines": removed_lines,
            "only_div_phi_U_changed": bool(
                len(changed_lines) == 1
                and changed_lines[0].strip() == TREATMENT_SCHEME
                and len(removed_lines) == 1
                and removed_lines[0].strip() == BASELINE_SCHEME
            ),
        },
        "baseline_fv_schemes_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "treatment_fv_schemes_sha256": _sha256(schemes),
        "adjoint_structural": structural,
        "summary": {
            "preflight_pass": bool(
                structural["pass"]
                and len(changed_lines) == 1
                and changed_lines[0].strip() == TREATMENT_SCHEME
                and len(removed_lines) == 1
                and removed_lines[0].strip() == BASELINE_SCHEME
            ),
            "diagnostic_allowed": bool(
                structural["pass"]
                and len(changed_lines) == 1
                and changed_lines[0].strip() == TREATMENT_SCHEME
                and len(removed_lines) == 1
                and removed_lines[0].strip() == BASELINE_SCHEME
            ),
            "solver_started": False,
        },
        "claims_not_supported": ["no solver has run; this is a structural preflight only"],
    }
    PREFLIGHT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


def _grid(spec) -> CartesianCellGrid:
    bounds = spec.grid.domain_bounds_m
    voxel = float(spec.grid.voxel_size_m)
    shape = tuple(
        int(round((float(bounds.upper[index]) - float(bounds.lower[index])) / voxel))
        for index in range(3)
    )
    return CartesianCellGrid(origin=tuple(bounds.lower), spacing=(voxel, voxel, voxel), cell_shape=shape)


def _clean_for_solver(case_dir: Path) -> None:
    for relative in ("postProcessing", "log.simpleFoam", "stage_v_qualification.json", "constant/dynamicMeshDict"):
        path = case_dir / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
    for child in case_dir.iterdir():
        if child.is_dir() and child.name not in {"0", "constant", "system", "tools"}:
            shutil.rmtree(child)


def _qualify(case_dir: Path) -> dict:
    path = write_stage_v_qualification(case_dir)
    return ca.load_json(path)


def _side_responses(case_dir: Path) -> tuple[float | None, float | None]:
    qualification = _qualify(case_dir)
    responses = qualification.get("force_stationarity", {}).get("responses", {})
    return (
        responses.get("Cd", {}).get("mean"),
        responses.get("downforce", {}).get("mean"),
    )




def _build_diagnostic(*, side_records: dict, qualification: dict, result: dict, analytic_vectors: dict) -> dict:
    """Correct ratio comparison: each ratio uses its own scheme's analytic value."""

    original_rows = {
        (response, row["direction"], float(row["epsilon"])): row
        for response, rows in result["rows"].items()
        for row in rows
    }
    diagnostic: dict[str, dict] = {}
    for response in ("drag", "downforce"):
        response_key = "Cd" if response == "drag" else "downforce"
        for direction_name in DIRECTIONS:
            plus = side_records[f"{direction_name}__plus"]
            minus = side_records[f"{direction_name}__minus"]
            vector = np.asarray(qualification["directions"][direction_name]["values"], dtype=np.float64)
            analytic_linear = float(np.dot(analytic_vectors[response], vector))
            original = original_rows[(response, direction_name, EPSILON)]
            analytic_upwind = float(original["analytic"])
            if not (plus["pass"] and minus["pass"]):
                diagnostic[f"{response}__{direction_name}"] = {"status": "side_failure"}
                continue
            fd = (float(plus[response_key]) - float(minus[response_key])) / (2.0 * EPSILON)
            diagnostic[f"{response}__{direction_name}"] = {
                "status": "ok",
                "analytic_linearUpwind": analytic_linear,
                "analytic_upwind": analytic_upwind,
                "fd_linearUpwind": fd,
                "fd_upwind": float(original["fd"]),
                "ratio_linearUpwind": fd / analytic_linear if analytic_linear else None,
                "ratio_upwind": float(original["fd"]) / analytic_upwind if analytic_upwind else None,
                "distance_to_one_linearUpwind": abs(fd / analytic_linear - 1.0) if analytic_linear else None,
                "distance_to_one_upwind": abs(float(original["fd"]) / analytic_upwind - 1.0)
                if analytic_upwind
                else None,
            }
    return diagnostic

def recompute() -> dict:
    """Rebuild the comparison block from the preserved side records (no CFD)."""

    if EVIDENCE.exists():
        raise SystemExit("discretization diagnostic evidence already exists")
    if not PRESERVED.exists():
        raise SystemExit("preserved diagnostic evidence is missing")
    preserved = ca.load_json(PRESERVED)
    qualification = ca.load_json(QUALIFICATION)
    result = ca.load_json(RESULT)
    derivative_paths = sorted((D3_ADJOINT / "optimisation" / "derivatives").glob("*"))
    derivatives = {
        "drag": parse_derivative_file(next(path for path in derivative_paths if "adjDrag" in path.name), expected_solver="adjDrag"),
        "downforce": parse_derivative_file(next(path for path in derivative_paths if "adjDownforce" in path.name), expected_solver="adjDownforce"),
    }
    active_ids = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    analytic_vectors = {
        response: response_derivative_vector(derivative, active_ids=active_ids, objective_sign=OBJECTIVE_SIGNS[response])
        for response, derivative in derivatives.items()
    }
    diagnostic = _build_diagnostic(
        side_records=preserved["sides"],
        qualification=qualification,
        result=result,
        analytic_vectors=analytic_vectors,
    )
    failing = [
        record
        for record in diagnostic.values()
        if record["status"] == "ok"
        and record["distance_to_one_upwind"] > 0.05
        and record["distance_to_one_linearUpwind"] <= 0.05
    ]
    worsened_controls = [
        record
        for record in diagnostic.values()
        if record["status"] == "ok"
        and record["distance_to_one_upwind"] <= 0.05
        and record["distance_to_one_linearUpwind"] > 0.05
    ]
    evidence = dict(preserved)
    evidence["comparison_correction"] = {
        "note": (
            "the first analysis divided the upwind FD by the linearUpwind analytic; each ratio now "
            "uses its own scheme's analytic value. CFD side records are unchanged."
        ),
    }
    evidence["diagnostic"] = diagnostic
    evidence["interpretation"] = {
        "n_rows": len(diagnostic),
        "n_improved_across_the_gate": len(failing),
        "n_worsened_controls": len(worsened_controls),
        "supports_discretization_cause": bool(failing and not worsened_controls),
        "diagnostic_pass": preserved["interpretation"]["diagnostic_pass"],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["interpretation"], indent=2))
    return evidence


def run() -> dict:
    if EVIDENCE.exists():
        raise SystemExit("discretization diagnostic evidence already exists")
    preflight_artifact = ca.load_json(PREFLIGHT)
    if preflight_artifact["summary"].get("diagnostic_allowed") is not True:
        raise SystemExit("diagnostic preflight did not allow the run")
    work_f = ca.load_json(WORK_F_MANIFEST)
    qualification = ca.load_json(QUALIFICATION)
    result = ca.load_json(RESULT)
    catalog = ca.load_json(CATALOG)
    spec = load_problem_spec(SPEC)
    grid = _grid(spec)
    basis = catalog["shared_catalog"]["surface_basis"]
    active_ids = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    timeout = int(work_f["solver_budget"]["solver_timeout_seconds"])

    # 1. linearUpwind base primal
    (D3_BASE / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
    base_run = run_openfoam_case(D3_BASE, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=work_f["openfoam_image"])
    base_qualification = _qualify(D3_BASE)
    base_pass = bool(getattr(base_run, "returncode", None) == 0 and base_qualification.get("qualified"))
    if not base_pass:
        raise SystemExit("linearUpwind base primal failed; scheme not adopted")

    # 2. linearUpwind adjoints
    (D3_ADJOINT / "Allrun").write_text(ADJOINT_ALLRUN, encoding="utf-8", newline="\n")
    adjoint_run = run_openfoam_case(D3_ADJOINT, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=work_f["openfoam_image"])
    adjoint_log = (D3_ADJOINT / "log.adjointOptimisationFoam").read_text(encoding="utf-8", errors="replace")
    derivative_paths = sorted((D3_ADJOINT / "optimisation" / "derivatives").glob("*"))
    derivatives = {
        "drag": parse_derivative_file(next(path for path in derivative_paths if "adjDrag" in path.name), expected_solver="adjDrag"),
        "downforce": parse_derivative_file(next(path for path in derivative_paths if "adjDownforce" in path.name), expected_solver="adjDownforce"),
    }
    analytic_vectors = {
        response: response_derivative_vector(derivative, active_ids=active_ids, objective_sign=OBJECTIVE_SIGNS[response])
        for response, derivative in derivatives.items()
    }
    adjoint_ok = all(
        f"{name} solution converged in" in adjoint_log
        for name in ("adjDownforce", "adjDrag")
    ) and getattr(adjoint_run, "returncode", None) == 0

    # 3. six perturbation sides on the linearUpwind base
    if D3_PERTURBATIONS.exists():
        shutil.rmtree(D3_PERTURBATIONS)
    D3_PERTURBATIONS.mkdir(parents=True)
    baseline_patch = extract_patch_surface(D3_BASE, time_name="constant")
    baseline_points = D3_BASE / "constant" / "polyMesh" / "points"
    side_records: dict[str, dict] = {}
    for direction_name in DIRECTIONS:
        vector = np.asarray(qualification["directions"][direction_name]["values"], dtype=np.float64)
        for sign, label in ((1.0, "plus"), (-1.0, "minus")):
            case_dir = D3_PERTURBATIONS / f"{direction_name}__{label}"
            movement = build_control_point_movement(
                direction=vector,
                active_var_ids=active_ids,
                n_control_points=(8, 8, 8),
                epsilon=EPSILON,
                sign=sign,
            )
            shutil.copytree(D3_BASE, case_dir)
            (case_dir / "constant" / "dynamicMeshDict").write_text(
                build_dynamic_mesh_dict(
                    box_min=tuple(float(value) for value in basis["box_m"]["min"]),
                    box_max=tuple(float(value) for value in basis["box_m"]["max"]),
                    n_cps=tuple(int(value) for value in basis["control_points"]),
                    degree=(3, 3, 3),
                ),
                encoding="utf-8",
                newline="\n",
            )
            (case_dir / "constant" / "controlPointsMovement").write_text(
                movement_to_text(movement), encoding="utf-8", newline="\n"
            )
            (case_dir / "tools").mkdir(exist_ok=True)
            shutil.copyfile(MORPHER, case_dir / "tools" / "moveControlPoints")
            (case_dir / "tools" / "moveControlPoints").chmod(0o755)
            (case_dir / "Allrun").write_text(
                "#!/usr/bin/env bash\nset -eo pipefail\ntools/moveControlPoints | tee log.moveControlPoints\n"
                "checkMesh -allGeometry -allTopology | tee log.checkMesh\n",
                encoding="utf-8",
                newline="\n",
            )
            morpher_run = run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=work_f["openfoam_image"])
            check_mesh = parse_check_mesh_qualified(
                (case_dir / "log.checkMesh").read_text(encoding="utf-8", errors="replace"),
                profile=STAGE_V_QUALIFICATION_PROFILE_V1,
            )
            moved_patch = extract_patch_surface(case_dir, time_name="0")
            geometry = surface_geometry_checks(baseline=baseline_patch, moved=moved_patch, spec=spec, grid=grid)
            immobility = fixed_patch_immobility(
                case_dir=case_dir, baseline_points=baseline_points, moved_points=case_dir / "0" / "polyMesh" / "points"
            )
            _clean_for_solver(case_dir)
            (case_dir / "Allrun").write_text(SOLVE_ONLY_ALLRUN, encoding="utf-8", newline="\n")
            primal_run = run_openfoam_case(case_dir, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=work_f["openfoam_image"])
            cd_mean, downforce_mean = _side_responses(case_dir)
            side_records[f"{direction_name}__{label}"] = {
                "direction": direction_name,
                "sign": label,
                "case_dir": str(case_dir.relative_to(ROOT)),
                "morpher_returncode": getattr(morpher_run, "returncode", None),
                "primal_returncode": getattr(primal_run, "returncode", None),
                "check_mesh_qualified": bool(check_mesh.get("qualified")),
                "geometry_pass": bool(geometry["pass"]),
                "immobility_pass": bool(immobility["pass"]),
                "Cd": cd_mean,
                "downforce": downforce_mean,
                "pass": bool(
                    getattr(morpher_run, "returncode", None) == 0
                    and getattr(primal_run, "returncode", None) == 0
                    and check_mesh.get("qualified")
                    and geometry["pass"]
                    and immobility["pass"]
                    and cd_mean is not None
                    and downforce_mean is not None
                ),
            }
            print("d3 side", direction_name, label, side_records[f"{direction_name}__{label}"]["pass"], flush=True)

    # 4. ratios and per-direction comparison with the original upwind result
    diagnostic = _build_diagnostic(
        side_records=side_records,
        qualification=qualification,
        result=result,
        analytic_vectors=analytic_vectors,
    )
    failing = [
        record
        for record in diagnostic.values()
        if record["status"] == "ok"
        and record["distance_to_one_upwind"] > 0.05
        and record["distance_to_one_linearUpwind"] <= 0.05
    ]
    worsened_controls = [
        record
        for record in diagnostic.values()
        if record["status"] == "ok"
        and record["distance_to_one_upwind"] <= 0.05
        and record["distance_to_one_linearUpwind"] > 0.05
    ]
    evidence = {
        "kind": "stage_s_work_f_discretization_diagnostic",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "preflight": {"path": str(PREFLIGHT.relative_to(ROOT)), "sha256": _sha256(PREFLIGHT)},
        "base_primal": {
            "returncode": getattr(base_run, "returncode", None),
            "qualified": bool(base_qualification.get("qualified")),
            "reasons": base_qualification.get("reasons"),
            "responses": {
                name: {"mean": value.get("mean"), "status": value.get("status")}
                for name, value in base_qualification.get("force_stationarity", {}).get("responses", {}).items()
            },
        },
        "adjoint": {
            "returncode": getattr(adjoint_run, "returncode", None),
            "converged": bool(adjoint_ok),
            "derivative_files": {
                response: {"name": Path(derivative.path).name, "sha256": derivative.sha256}
                for response, derivative in derivatives.items()
            },
        },
        "sides": side_records,
        "diagnostic": diagnostic,
        "interpretation": {
            "n_rows": len(diagnostic),
            "n_improved_across_the_gate": len(failing),
            "n_worsened_controls": len(worsened_controls),
            "supports_discretization_cause": bool(failing and not worsened_controls),
            "diagnostic_pass": bool(base_pass and adjoint_ok and all(record["pass"] for record in side_records.values())),
        },
        "summary": {
            "diagnostic_pass": bool(base_pass and adjoint_ok and all(record["pass"] for record in side_records.values())),
            "derivative_qualified": False,
            "shape_update_allowed": False,
            "original_verdict_unchanged": True,
        },
        "claims_supported": [
            "the registered linearUpwind factor was run on an independent base/adjoint lineage with all gates recorded",
        ],
        "claims_not_supported": [
            "this bounded diagnostic does not qualify the derivative or authorize a shape update",
        ],
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F bounded discretization diagnostic (D3)")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.preflight:
        preflight()
    elif args.run:
        run()
    elif args.recompute:
        recompute()
    else:
        parser.error("specify --register, --preflight or --run")


if __name__ == "__main__":
    main()
