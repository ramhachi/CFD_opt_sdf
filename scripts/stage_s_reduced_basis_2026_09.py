"""Stage S reduced-basis FD architecture S0 registration and S1 preflight.

``--register`` (S0, solver-free) fixes the immutable contract: the versioned
reduced-basis ProblemSpec with the canonical objective ``maximize downforce /
J = -downforce`` and drag report-only, the K=16 mode-space design map, the
geometry-only mode generation rules, the physical epsilon ladder, the S2/S3/S4
calibration/gradient/holdout rules and the one-step rules. No solver runs.

``--preflight`` (S1, solver-free) generates the frequency-ordered
y-symmetry-preserving sine-mode candidates, measures each candidate's design
surface normal-displacement efficiency with the registered morpher (Pass A),
normalizes the survivors to unit maximum normal displacement per unit mode
coefficient, and runs the full plus/minus max-epsilon geometry/mesh/realized
motion preflight (Pass B). Fewer than 16 surviving modes stops the campaign.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.fixed_grid_contract import CartesianCellGrid  # noqa: E402
from cfd_sdf.problem_spec import load_problem_spec  # noqa: E402
from cfd_sdf.stage_s_adjoint_case import build_dynamic_mesh_dict  # noqa: E402
from cfd_sdf.stage_s_perturbation import (  # noqa: E402
    extract_patch_surface,
    fixed_patch_immobility,
    movement_to_text,
    parse_check_mesh_qualified,
    surface_geometry_checks,
)
from cfd_sdf.stage_s_realized_direction import (  # noqa: E402
    DIRECTION_CP_ABS_TOLERANCE_M,
    EVEN_COMPONENT_ABS_TOLERANCE_M,
    active_mask_from_ids,
    audit_case,
    direction_comparison,
    direction_to_cp_space,
    read_control_points_csv,
    read_control_points_file,
    read_movement_file,
)
from cfd_sdf.stage_s_reduced_basis import (  # noqa: E402
    CANDIDATE_COUNT,
    EPSILON_LADDER_M,
    K_MODES,
    MIN_NORMAL_EFFICIENCY,
    NORMAL_DISPLACEMENT_RELATIVE_TOLERANCE,
    REFERENCE_AMPLITUDE_M,
    canonical_sign,
    holdout_mode_directions,
    mode_candidates,
    mode_sha256,
    mode_to_movement,
    normal_displacement,
    sine_mode_vector,
)

WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
A0_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_fi_formulation_diagnostic_manifest_2026_09.json"
A1_EVIDENCE = ROOT / "docs/evidence/stage_s_work_f_fi_formulation_diagnostic_2026_09.json"
ARCHITECTURE_MEMO = ROOT / "docs/stage_s_work_f_architecture_decision_2026_09_25.md"
ORIGINAL_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar.yaml"
REDUCED_SPEC = ROOT / "work/stage_sv_laminar/project_matched_re_laminar_reduced_basis_v1.yaml"
BASE_CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"
MORPHER = ROOT / "work/stage_s_work_f_v1/tools/moveControlPoints"
BASE_CP_CATALOG = (
    ROOT / "work/stage_s_work_f_v1/adjoint/base/optimisation/controlPoints/boxcpsBsplines0.csv"
)
DIAGNOSIS_ROOT = ROOT / "work/stage_s_work_f_v1/diagnosis/reduced_basis"
SCRATCH = DIAGNOSIS_ROOT / "scratch"
MODES_DIR = DIAGNOSIS_ROOT / "modes"
MANIFEST = ROOT / "docs/evidence/stage_s_reduced_basis_fd_manifest_2026_09.json"
EVIDENCE = ROOT / "docs/evidence/stage_s_reduced_basis_mode_preflight_2026_09.json"
PRESERVED_FIRST_ATTEMPT = (
    ROOT / "docs/evidence/stage_s_reduced_basis_mode_preflight_scratch_reuse_error_2026_09.json"
)
PRESERVED_SECOND_ATTEMPT = (
    ROOT / "docs/evidence/stage_s_reduced_basis_mode_preflight_rate_gate_error_2026_09.json"
)
ALLRUN_PASS_A = (
    "#!/usr/bin/env bash\n"
    "set -eo pipefail\n"
    "tools/moveControlPoints | tee log.moveControlPoints\n"
)
ALLRUN_PASS_B = (
    "#!/usr/bin/env bash\n"
    "set -eo pipefail\n"
    "tools/moveControlPoints | tee log.moveControlPoints\n"
    "checkMesh -allGeometry -allTopology | tee log.checkMesh\n"
)
CANONICAL_OBJECTIVE = {
    "declared": "maximize downforce",
    "canonical_J": "J = -downforce",
    "response_id": "downforce",
    "sense": "maximize",
    "drag": "report_only",
    "constraints": [],
    "post_hoc_rule": "adding a drag constraint or changing the objective requires a new contract",
}


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _grid(spec) -> CartesianCellGrid:
    bounds = spec.grid.domain_bounds_m
    voxel = float(spec.grid.voxel_size_m)
    shape = tuple(
        int(round((float(bounds.upper[index]) - float(bounds.lower[index])) / voxel))
        for index in range(3)
    )
    return CartesianCellGrid(origin=tuple(bounds.lower), spacing=(voxel, voxel, voxel), cell_shape=shape)


def _build_reduced_spec() -> dict:
    raw = yaml.safe_load(ORIGINAL_SPEC.read_text(encoding="utf-8"))
    reduced = copy.deepcopy(raw)
    reduced["problem_id"] = f"{raw['problem_id']}_reduced_basis_v1"
    reduced["objectives"] = [
        {
            "id": "maximize_downforce",
            "sense": "maximize",
            "terms": [
                {
                    "coefficient": 1.0,
                    "flow_case_id": "matched_re_laminar",
                    "response_id": "downforce",
                }
            ],
        }
    ]
    return reduced


def _ensure_reduced_spec() -> dict:
    reduced = _build_reduced_spec()
    if REDUCED_SPEC.exists():
        existing = yaml.safe_load(REDUCED_SPEC.read_text(encoding="utf-8"))
        if existing != reduced:
            raise SystemExit("the existing reduced-basis spec does not match the deterministic construction")
    else:
        REDUCED_SPEC.write_text(
            yaml.safe_dump(reduced, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    original = yaml.safe_load(ORIGINAL_SPEC.read_text(encoding="utf-8"))
    diff = sorted(key for key in set(original) | set(reduced) if original.get(key) != reduced.get(key))
    if diff != ["objectives", "problem_id"]:
        raise SystemExit(f"the reduced spec differs beyond the objective contract: {diff}")
    spec = load_problem_spec(REDUCED_SPEC)
    objectives = {objective.id: objective for objective in spec.objectives}
    if set(objectives) != {"maximize_downforce"}:
        raise SystemExit("the reduced spec does not declare exactly the canonical objective")
    objective = objectives["maximize_downforce"]
    if objective.sense != "maximize":
        raise SystemExit("the canonical objective sense is not maximize")
    terms = {term.response_id: term for term in objective.terms}
    if set(terms) != {"downforce"} or float(terms["downforce"].coefficient) != 1.0:
        raise SystemExit("the canonical objective terms are not exactly +1 downforce")
    if any("drag" in objective.id for objective in spec.objectives):
        raise SystemExit("drag must not appear as an objective")
    if spec.constraints:
        raise SystemExit("the reduced-basis contract registers no constraints")
    return {
        "path": str(REDUCED_SPEC.relative_to(ROOT)),
        "sha256": _sha256(REDUCED_SPEC),
        "original": {"path": str(ORIGINAL_SPEC.relative_to(ROOT)), "sha256": _sha256(ORIGINAL_SPEC)},
        "diff_keys": diff,
        "objective": CANONICAL_OBJECTIVE,
        "declared_equals_evaluated": {
            "declared": "maximize downforce: coefficient +1 on the declared downforce response",
            "evaluated": (
                "centered FD of the downforce response in mode space; the canonical step direction "
                "maximizes downforce, i.e. minimizes J = -downforce; drag is recorded but never optimized"
            ),
            "response_identity": "the primal forceCoeffs downforce response (-Cl) used by the FD side",
        },
    }


def register() -> dict:
    if MANIFEST.exists():
        raise SystemExit("reduced-basis manifest already exists; refuse overwrite")
    spec_record = _ensure_reduced_spec()
    work_f = ca.load_json(WORK_F_MANIFEST)
    manifest = {
        "kind": "stage_s_reduced_basis_fd_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "architecture": {
            "id": "stage_s_reduced_basis_fd_v1",
            "class": "bounded reduced-basis one-step architecture",
            "not": [
                "production optimizer",
                "qualified Stage S optimizer",
                "multi-step optimizer",
            ],
        },
        "inputs": {
            "a0_manifest": {"path": str(A0_MANIFEST.relative_to(ROOT)), "sha256": _sha256(A0_MANIFEST)},
            "a1_evidence": {"path": str(A1_EVIDENCE.relative_to(ROOT)), "sha256": _sha256(A1_EVIDENCE)},
            "architecture_memo": {
                "path": str(ARCHITECTURE_MEMO.relative_to(ROOT)),
                "sha256": _sha256(ARCHITECTURE_MEMO),
            },
            "work_f_manifest": {"path": str(WORK_F_MANIFEST.relative_to(ROOT)), "sha256": _sha256(WORK_F_MANIFEST)},
            "catalog": {"path": str(CATALOG.relative_to(ROOT)), "sha256": _sha256(CATALOG)},
            "qualification": {"path": str(QUALIFICATION.relative_to(ROOT)), "sha256": _sha256(QUALIFICATION)},
            "original_problem_spec": spec_record["original"],
            "reduced_basis_problem_spec": {
                "path": spec_record["path"],
                "sha256": spec_record["sha256"],
                "diff_keys": spec_record["diff_keys"],
            },
            "morpher_utility": {"path": str(MORPHER.relative_to(ROOT)), "sha256": _sha256(MORPHER)},
            "baseline_case": {"path": str(BASE_CASE.relative_to(ROOT))},
            "base_control_point_catalog": {
                "path": str(BASE_CP_CATALOG.relative_to(ROOT)),
                "sha256": _sha256(BASE_CP_CATALOG),
            },
        },
        "openfoam_image": work_f["openfoam_image"],
        "openfoam_image_id": work_f["openfoam_image_id"],
        "objective_contract": {
            **spec_record["objective"],
            "declared_equals_evaluated": spec_record["declared_equals_evaluated"],
        },
        "design_space": {
            "parameterization": "the registered volumetricBSplines morpher is reused unchanged",
            "k_modes": K_MODES,
            "map": "delta_cp = B q, B in R^(648 x 16)",
            "normalization": (
                "each mode is scaled so that the maximum absolute normal displacement of the "
                "design surface per unit mode coefficient is 1 m"
            ),
            "q_change_policy": "K is fixed at 16; changing K requires a new contract",
        },
        "mode_generation": {
            "source": "geometry-only low-frequency discrete sine modes on the active 6x6x6 lattice",
            "candidate_count": CANDIDATE_COUNT,
            "ordering": "frequency a^2+b^2+c^2 then (a,b,c) then axis x,y,z",
            "symmetry_rule": "y-mirror preserving only: x/z components need b odd, y component needs b even",
            "boundary": "zero on the boundary control points",
            "sign_rule": "the largest-magnitude active component is positive (deterministic)",
            "selection_rule": (
                "iterate candidates in order; exclude a candidate if its normal-displacement "
                "efficiency is below 0.01 or if either side of its plus/minus max-epsilon preflight "
                "fails; the final modes are the first 16 survivors"
            ),
            "min_normal_efficiency": MIN_NORMAL_EFFICIENCY,
            "reference_amplitude_m": REFERENCE_AMPLITUDE_M,
            "replacement_rule": (
                "no replacement after any flow response is read; fewer than 16 surviving modes "
                "stops the campaign and requires a new generator version"
            ),
        },
        "epsilon_ladder_m": list(EPSILON_LADDER_M),
        "s2_calibration": {
            "modes": "lowest, middle and highest frequency of the selected 16 (deterministic)",
            "design": "3 modes x 4 epsilons x 2 signs, at most 24 primals",
            "requirements": [
                "every side passes the geometry/mesh/solver/stationarity gates",
                "sign consistency across epsilons",
                "epsilon plateau within the registered tolerance",
                "response change above the registered noise floor",
                "plus/minus odd component dominates the even component",
                "near-zero rule applied to both responses",
            ],
            "primary_epsilon_rule": (
                "the largest ladder epsilon for which all three calibration modes satisfy every "
                "requirement; if none does, stop without a gradient"
            ),
        },
        "s3_gradient": {
            "design": "all 16 modes at the selected primary epsilon, plus/minus, reusing S2 runs",
            "max_primals": 32,
            "outputs": ["downforce gradient in mode space (canonical)", "drag gradient (report-only)"],
            "claims": "gradient qualified in the span of B only",
            "claims_not_supported": [
                "the original 648-dimensional adjoint gradient is qualified",
                "the B-spline adjoint is repaired",
                "arbitrary shape directions are qualified",
                "a production or multi-step Stage S optimizer exists",
            ],
        },
        "s4_holdout": {
            "directions": "2 random mode directions from the manifest hash + 1 downforce projected-gradient direction",
            "seed_rule": "seed_i = first 8 bytes (big-endian) of sha256(manifest_sha256 + ':holdout:mode:' + i), i >= 1",
            "sides": "plus and minus",
            "primals": 6,
            "requirements": [
                "relative error <= 5% for both responses",
                "sign agreement",
                "near-zero rule",
                "all side geometry/mesh/solver/stationarity gates pass",
                "the calibration plateau rule holds",
            ],
            "stop": "any fail or unresolved direction stops the shape step",
        },
        "s5_one_step": {
            "manifest": "a separate one-step manifest must be registered after a complete S4 pass",
            "registers": [
                "objective and canonical sign",
                "mode-space direction",
                "trust radius",
                "maximum control-point and surface displacement",
                "predicted downforce and drag change",
                "volume, width, clearance, connectivity",
                "mesh gate",
                "primal residual and stationarity",
                "actual-response acceptance rule",
                "rollback rule",
            ],
            "acceptance": "the actual new-shape primal, never the predicted value",
            "multi_step": "a successful step never starts a multi-step optimization",
        },
        "flags": {
            "original_adjoint_derivative_qualified": False,
            "reduced_basis_fd_qualified": "pending",
            "shape_update_allowed": False,
        },
        "budget": {
            "s0_solver_runs": 0,
            "s1_morpher_runs_max": 2 * CANDIDATE_COUNT,
            "s1_flow_runs": 0,
            "s2_primals_max": 24,
            "s3_primals_max": 32,
            "s4_primals": 6,
            "s5_shape_steps_max": 1,
        },
        "stop_conditions": [
            "fewer than 16 modes survive the S1 preflight",
            "any baseline lineage, geometry, mesh, convergence or stationarity gate fails",
            "the S2 calibration selects no primary epsilon",
            "the S4 holdout fails or remains unresolved",
            "adding a factor, constraint, scale or direction after seeing a response",
        ],
        "claims_not_supported": [
            "this registration is a design/problem contract and contains no flow evidence",
            "a qualified Stage S derivative or shape improvement is not claimed",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)}, indent=2))
    return manifest


def _verify_inputs(manifest: dict) -> None:
    for name, record in manifest["inputs"].items():
        if "sha256" in record and _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"registered input changed: {name}")


def _prepare_case(case_dir: Path, movement: np.ndarray, basis: dict, allrun: str) -> None:
    if not case_dir.exists():
        case_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(BASE_CASE, case_dir)
        for relative in ("postProcessing", "log.simpleFoam", "stage_v_qualification.json"):
            path = case_dir / relative
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
        for child in list(case_dir.iterdir()):
            if child.is_dir() and child.name not in {"0", "constant", "system"}:
                shutil.rmtree(child)
    # a reused case must restart from the unmoved constant/polyMesh and the
    # box-initialized control points. The morpher writes the moved mesh to
    # 0/polyMesh and the realized control points to 0/uniform, and on restart
    # it would read both and compound one mode on top of the previous one.
    for relative in ("0/polyMesh", "0/uniform", "0/parametricCoordinatesbox"):
        path = case_dir / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
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
    (case_dir / "Allrun").write_text(allrun, encoding="utf-8", newline="\n")


def _run_morpher(case_dir: Path, timeout: int, image: str) -> dict:
    run = run_openfoam_case(
        case_dir, backend="docker", dry_run=False, timeout_seconds=timeout, docker_image=image
    )
    return {
        "returncode": getattr(run, "returncode", None),
        "timed_out": getattr(run, "timed_out", None),
    }


def preflight() -> dict:
    if EVIDENCE.exists():
        raise SystemExit("reduced-basis mode preflight evidence already exists; refuse overwrite")
    manifest = ca.load_json(MANIFEST)
    _verify_inputs(manifest)
    work_f = ca.load_json(WORK_F_MANIFEST)
    catalog = ca.load_json(CATALOG)
    qualification = ca.load_json(QUALIFICATION)
    spec = load_problem_spec(REDUCED_SPEC)
    grid = _grid(spec)
    basis = catalog["shared_catalog"]["surface_basis"]
    active_ids = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    timeout = int(work_f["solver_budget"]["solver_timeout_seconds"])
    image = work_f["openfoam_image"]
    base_cp = read_control_points_csv(BASE_CP_CATALOG)
    mask = active_mask_from_ids(active_ids)
    baseline_patch = extract_patch_surface(BASE_CASE, time_name="constant")
    baseline_points = BASE_CASE / "constant" / "polyMesh" / "points"

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    if MODES_DIR.exists():
        shutil.rmtree(MODES_DIR)

    candidates = mode_candidates(CANDIDATE_COUNT)
    candidate_records: list[dict] = []
    selected: list[dict] = []
    for candidate in candidates:
        record: dict = {"candidate": candidate.to_dict()}
        raw, flipped = canonical_sign(sine_mode_vector(candidate, active_ids=active_ids))
        record["raw_vector_sha256"] = mode_sha256(raw)
        record["sign_flipped"] = flipped
        movement = mode_to_movement(
            raw, active_ids=active_ids, coefficient=REFERENCE_AMPLITUDE_M, sign=1.0
        )
        _prepare_case(SCRATCH, movement, basis, ALLRUN_PASS_A)
        run_record = _run_morpher(SCRATCH, timeout, image)
        record["pass_a"] = run_record
        if run_record["returncode"] != 0:
            record.update({"selected": False, "exclusion_reason": "morpher_failure"})
            candidate_records.append(record)
            continue
        moved_patch = extract_patch_surface(SCRATCH, time_name="0")
        displacement = normal_displacement(
            base_vertices=baseline_patch.vertices,
            faces=baseline_patch.faces,
            moved_vertices=moved_patch.vertices,
        )
        efficiency = float(displacement["max_abs_normal_displacement_m"]) / REFERENCE_AMPLITUDE_M
        record["pass_a"].update(
            {
                "max_abs_normal_displacement_m": displacement["max_abs_normal_displacement_m"],
                "normal_efficiency": efficiency,
            }
        )
        if efficiency < MIN_NORMAL_EFFICIENCY:
            record.update({"selected": False, "exclusion_reason": "efficiency_below_minimum"})
            candidate_records.append(record)
            continue

        normalized = raw / efficiency
        record["normalization_factor"] = 1.0 / efficiency
        record["normalized_vector_sha256"] = mode_sha256(normalized)
        preflight: dict = {}
        displacement_by_sign: dict[str, dict] = {}
        realized_by_sign: dict[str, np.ndarray] = {}
        case_by_sign: dict[str, Path] = {}
        for sign, label in ((1.0, "plus"), (-1.0, "minus")):
            case_dir = MODES_DIR / f"{candidate.name}__{label}"
            mode_movement = mode_to_movement(
                normalized, active_ids=active_ids, coefficient=REFERENCE_AMPLITUDE_M, sign=sign
            )
            _prepare_case(case_dir, mode_movement, basis, ALLRUN_PASS_B)
            run_entry = _run_morpher(case_dir, timeout, image)
            moved = extract_patch_surface(case_dir, time_name="0")
            dn = normal_displacement(
                base_vertices=baseline_patch.vertices,
                faces=baseline_patch.faces,
                moved_vertices=moved.vertices,
            )
            displacement_by_sign[label] = dn
            realized_by_sign[label] = read_control_points_file(
                case_dir / "0" / "uniform" / "volumetricBSplines" / "boxcpsBsplines"
            )
            prescribed = read_movement_file(case_dir / "constant" / "controlPointsMovement")
            realized_checks = audit_case(
                base=base_cp, realized=realized_by_sign[label], prescribed=prescribed, active_mask=mask
            )
            check_mesh = parse_check_mesh_qualified(
                (case_dir / "log.checkMesh").read_text(encoding="utf-8", errors="replace"),
                profile=STAGE_V_QUALIFICATION_PROFILE_V1,
            )
            geometry = surface_geometry_checks(
                baseline=baseline_patch, moved=moved, spec=spec, grid=grid
            )
            immobility = fixed_patch_immobility(
                case_dir=case_dir,
                baseline_points=baseline_points,
                moved_points=case_dir / "0" / "polyMesh" / "points",
            )
            normalized_displacement = (
                float(dn["max_abs_normal_displacement_m"]) / REFERENCE_AMPLITUDE_M
            )
            normalized_ok = bool(
                abs(normalized_displacement - 1.0) <= NORMAL_DISPLACEMENT_RELATIVE_TOLERANCE
            )
            preflight[label] = {
                "case_dir": str(case_dir.relative_to(ROOT)),
                "morpher_returncode": run_entry["returncode"],
                "check_mesh_qualified": bool(check_mesh.get("qualified")),
                "check_mesh": check_mesh,
                "geometry_pass": bool(geometry["pass"]),
                "geometry": geometry,
                "immobility_pass": bool(immobility["pass"]),
                "immobility": immobility,
                "realized_equals_prescribed": bool(realized_checks["realized_equals_prescribed"]),
                "boundary_fixed": bool(realized_checks["boundary_fixed"]),
                "inactive_zero": bool(realized_checks["inactive_zero"]),
                "max_abs_normal_displacement_m": dn["max_abs_normal_displacement_m"],
                "normalized_displacement": normalized_displacement,
                "normalized_displacement_ok": normalized_ok,
                "pass": bool(
                    run_entry["returncode"] == 0
                    and check_mesh.get("qualified")
                    and geometry["pass"]
                    and immobility["pass"]
                    and realized_checks["realized_equals_prescribed"]
                    and realized_checks["boundary_fixed"]
                    and realized_checks["inactive_zero"]
                    and normalized_ok
                ),
            }
            case_by_sign[label] = case_dir
        pair = (realized_by_sign["plus"] - realized_by_sign["minus"]) / (2.0 * REFERENCE_AMPLITUDE_M)
        direction_cp = direction_to_cp_space(normalized, active_ids)
        comparison = direction_comparison(
            direction_cp=direction_cp, delta_odd=pair, active_mask=mask
        )
        even_component = float(
            np.max(
                np.abs(
                    (realized_by_sign["plus"] + realized_by_sign["minus"]) / 2.0 - base_cp
                )
            )
        )
        movement_difference_m = float(comparison["max_abs_difference"]) * REFERENCE_AMPLITUDE_M
        # the registered physical criteria mirror the D1 pair rule; the
        # rate-space difference_ok uses DIRECTION_CP_ABS_TOLERANCE_M as a rate
        # tolerance and is not a pass gate
        preflight_ok = bool(
            preflight["plus"]["pass"]
            and preflight["minus"]["pass"]
            and comparison["cosine_ok"]
            and movement_difference_m <= DIRECTION_CP_ABS_TOLERANCE_M
            and even_component <= EVEN_COMPONENT_ABS_TOLERANCE_M
        )
        record.update(
            {
                "selected": preflight_ok,
                "exclusion_reason": None if preflight_ok else "preflight_failed",
                "preflight": preflight,
                "realized_direction": comparison,
                "realized_movement_difference_m": movement_difference_m,
                "realized_even_component_m": even_component,
            }
        )
        candidate_records.append(record)
        if preflight_ok:
            selected.append(
                {
                    "order": len(selected) + 1,
                    "candidate": candidate.to_dict(),
                    "vector_sha256": mode_sha256(normalized),
                    "normal_efficiency": efficiency,
                    "normalization_factor": 1.0 / efficiency,
                    "realized_direction_cosine": comparison["cosine_similarity"],
                    "preflight_plus_pass": preflight["plus"]["pass"],
                    "preflight_minus_pass": preflight["minus"]["pass"],
                    "max_abs_normal_displacement_plus_m": displacement_by_sign["plus"][
                        "max_abs_normal_displacement_m"
                    ],
                    "max_abs_normal_displacement_minus_m": displacement_by_sign["minus"][
                        "max_abs_normal_displacement_m"
                    ],
                    "case_dirs": {
                        label: str(case_by_sign[label].relative_to(ROOT)) for label in ("plus", "minus")
                    },
                }
            )
            if len(selected) == K_MODES:
                break

    manifest_sha = _sha256(MANIFEST)
    all_preflight_pass = bool(
        len(selected) == K_MODES
        and all(bool(record["preflight_plus_pass"] and record["preflight_minus_pass"]) for record in selected)
    )
    evidence = {
        "kind": "stage_s_reduced_basis_mode_preflight",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": manifest_sha},
        "baseline": {
            "case_dir": str(BASE_CASE.relative_to(ROOT)),
            "design_patch": "design_candidate",
            "n_patch_triangles": int(baseline_patch.faces.shape[0]),
            "n_patch_points": int(np.unique(baseline_patch.faces).size),
        },
        "candidates": candidate_records,
        "modes": selected,
        "holdout_rule_preview": {
            "seeds": [
                entry["seed"] for entry in holdout_mode_directions(manifest_sha, n_random=2)
            ],
            "rule": "seeds are derived from the manifest hash and fixed before any flow response",
        },
        "summary": {
            "n_candidates_evaluated": len(candidate_records),
            "n_modes_selected": len(selected),
            "all_preflight_pass": all_preflight_pass,
            "flow_campaign_allowed": all_preflight_pass,
            "reduced_basis_fd_qualified": "pending" if all_preflight_pass else False,
            "shape_update_allowed": False,
        },
        "claims_supported": [
            "the selected mode basis and its plus/minus geometry/mesh preflight are recorded solver-free",
        ],
        "claims_not_supported": [
            "no flow response, gradient or shape step exists; the derivative is not qualified",
        ],
    }
    preserved: list[dict] = []
    if PRESERVED_FIRST_ATTEMPT.exists():
        preserved.append(
            {
                "label": "first attempt: scratch reuse and missing frequency factors",
                "path": str(PRESERVED_FIRST_ATTEMPT.relative_to(ROOT)),
                "sha256": _sha256(PRESERVED_FIRST_ATTEMPT),
            }
        )
    if PRESERVED_SECOND_ATTEMPT.exists():
        preserved.append(
            {
                "label": "second attempt: rate-space difference_ok used as a pass gate",
                "path": str(PRESERVED_SECOND_ATTEMPT.relative_to(ROOT)),
                "sha256": _sha256(PRESERVED_SECOND_ATTEMPT),
            }
        )
    if preserved:
        evidence["method_correction"] = {
            "preserved_attempts": preserved,
            "note": (
                "implementation corrections before any flow response: (1) the first attempt "
                "reused one scratch case, so the morpher read the previously moved 0/polyMesh "
                "and the realized control points in 0/uniform and compounded modes, and the "
                "sine generator omitted the candidate frequency factors; (2) the second attempt "
                "applied the rate-space direction difference_ok (tolerance in rate units) as a "
                "pass gate instead of the registered physical-length D1 pair criteria "
                "(cosine plus movement difference and even component in metres). The final "
                "selection uses the physical criteria. No flow response is involved."
            ),
        }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage S reduced-basis S0/S1")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.preflight:
        preflight()
    else:
        parser.error("specify --register or --preflight")


if __name__ == "__main__":
    main()
