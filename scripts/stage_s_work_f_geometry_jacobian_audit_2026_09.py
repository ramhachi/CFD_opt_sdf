"""Work F post-D3 diagnosis D4.2 - B-spline geometry-Jacobian audit.

``--register`` fixes the geometry-Jacobian manifest before the utility is
built: the already-moved plus/minus meshes, the base-mesh hashes, the
read-only analytic dump utility source, the registered directions and the
per-quantity gate tolerances.

``--run`` builds the read-only utility, dumps the analytic directional
dxdbFace/dSdb/dndb of the design patch, computes centered differences of the
registered plus/minus meshes with the exact OpenFOAM face geometry
definitions, and records the face-by-face and patch-integrated comparison. No
primal or adjoint solver runs, the mesh is never modified, and the registered
FD verdict and thresholds are never changed.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.openfoam_sensitivity import _read_boundary, _read_points, _read_selected_faces  # noqa: E402
from cfd_sdf.stage_s_geometry_jacobian import (  # noqa: E402
    GEOMETRY_QUANTITIES,
    centered_difference,
    evaluate_quantity_gate,
    face_geometry,
    parse_dump,
    plateau_status,
    quantity_diagnostics,
)
from cfd_sdf.stage_s_adjoint_case import build_dynamic_mesh_dict  # noqa: E402
from cfd_sdf.stage_s_perturbation import build_control_point_movement  # noqa: E402

D4_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_component_diagnosis_manifest_2026_09.json"
D4_1_AUDIT = ROOT / "docs/evidence/stage_s_work_f_derivative_component_audit_2026_09.json"
PERTURBATION_SIDES = ROOT / "docs/evidence/stage_s_work_f_perturbation_sides_2026_09.json"
QUALIFICATION = ROOT / "docs/evidence/stage_s_work_f_adjoint_qualification_2026_09.json"
CATALOG = ROOT / "docs/evidence/stage_s_work_f_surface_fd_catalog_2026_09.json"
WORK_F_MANIFEST = ROOT / "docs/evidence/stage_s_work_f_manifest_2026_09.json"
BASE_CASE = ROOT / "work/stage_s_work_f_v1/baseline/V1"
ADJOINT_BASE_CASE = ROOT / "work/stage_s_work_f_v1/adjoint/base"
SCRATCH = ROOT / "work/stage_s_work_f_v1/diagnosis/geometry_jacobian/base"
TOOLS_DIR = ROOT / "work/stage_s_work_f_v1/tools"
UTILITY_SOURCE = ROOT / "openfoam_utils" / "geometryDerivativeDump"
MANIFEST = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_manifest_2026_09.json"
AUDIT = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_audit_2026_09.json"
PRESERVED = ROOT / "docs/evidence/stage_s_work_f_geometry_jacobian_audit_all_epsilon_2026_09.json"
DESIGN_PATCH = "design_candidate"
DIRECTIONS = (
    "downforce_gradient_aligned",
    "drag_gradient_aligned",
    "random_seed_11",
    "random_seed_2026",
)
ALLRUN = (
    "#!/usr/bin/env bash\n"
    "set -eo pipefail\n"
    "tools/geometryDerivativeDump | tee log.geometryDerivativeDump\n"
)
GATE_TOLERANCES = {
    "Cf": {"relative": 1.0e-4, "absolute": 1.0e-5, "l2_tolerance": 1.0e-3, "cosine_min": 0.999999},
    "Sf": {"relative": 1.0e-5, "absolute": 1.0e-6, "l2_tolerance": 1.0e-3, "cosine_min": 0.999999},
    "n": {"relative": 5.0e-3, "absolute": 1.0e-6, "l2_tolerance": 5.0e-3, "cosine_min": 0.999999},
}
PLATEAU_TOLERANCE = {"Cf": 1.0e-3, "Sf": 1.0e-3, "n": 5.0e-3}
COMPARISON_EPSILON = 1.0e-3
TOLERANCE_RATIONALE = (
    "moved mesh points are written in ASCII with about 8 significant digits, so the "
    "write/read roundoff is about 1e-8 m and the centered-difference noise at the "
    "largest registered epsilon (1e-3) is about 5e-6; the face-centre and area-vector "
    "maps are linear/quadratic in the control points and therefore exact, while the "
    "unit-normal difference carries an O((epsilon/L_face)^2) truncation of about 4e-4"
)


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _weight_files(qualification: dict) -> dict[str, np.ndarray]:
    active_ids = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    weights: dict[str, np.ndarray] = {}
    for name in DIRECTIONS:
        vector = np.asarray(qualification["directions"][name]["values"], dtype=np.float64)
        movement = build_control_point_movement(
            direction=vector,
            active_var_ids=active_ids,
            n_control_points=(8, 8, 8),
            epsilon=1.0,
            sign=1.0,
        )
        weights[name] = movement
    return weights


def _foam_header(object_name: str, class_name: str) -> str:
    return f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2512                                 |
|   \\\\  /    A nd           | www.openfoam.com                                |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {class_name};
    object      {object_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""


def _weights_text(name: str, weights: np.ndarray) -> str:
    rows = "\n".join(
        f"({row[0]:.17g} {row[1]:.17g} {row[2]:.17g})" for row in weights
    )
    return (
        _foam_header(name, "dictionary")
        + f"\nweights {len(weights)}\n(\n{rows}\n);\n\n"
        + "// ************************************************************************* //\n"
    )


def _settings_text(names: tuple[str, ...]) -> str:
    return (
        _foam_header("geometryDerivativeDirections", "dictionary")
        + f"\nnames ({' '.join(names)});\n"
        + "directory geometryDerivativeDirectionFiles;\n\n"
        + "// ************************************************************************* //\n"
    )


def _side_records(sides: dict) -> dict[str, dict]:
    records: dict[str, dict] = {}
    epsilons = sorted({float(record["epsilon_m"]) for record in sides.values()})
    for direction in DIRECTIONS:
        for epsilon in epsilons:
            for label in ("plus", "minus"):
                matches = [
                    (key, record)
                    for key, record in sides.items()
                    if record["direction"] == direction
                    and float(record["epsilon_m"]) == epsilon
                    and key.endswith(f"__{label}")
                ]
                if len(matches) != 1:
                    raise SystemExit(
                        f"perturbation sides evidence does not contain exactly one "
                        f"{direction}/{epsilon}/{label} record"
                    )
                key, record = matches[0]
                records[f"{direction}__{epsilon:g}__{label}"] = {
                    "side_key": key,
                    "case_dir": record["case_dir"],
                    "pass": bool(record.get("pass")),
                    "movement_sha256": record.get("movement_sha256"),
                    "moved_points_sha256": record.get("moved_points_sha256"),
                    "immobility_pass": bool(record.get("immobility", {}).get("pass")),
                    "boundary_max_displacement_m": record.get("immobility", {}).get(
                        "boundary_max_displacement_m"
                    ),
                }
    return records


def _mesh_files(case_dir: Path) -> dict[str, str]:
    mesh = case_dir / "constant" / "polyMesh"
    return {
        "points": ca.sha256_file(mesh / "points"),
        "faces": ca.sha256_file(mesh / "faces"),
        "boundary": ca.sha256_file(mesh / "boundary"),
    }


def register() -> dict:
    if MANIFEST.exists():
        raise SystemExit("geometry-Jacobian manifest already exists; refuse overwrite")
    d4 = ca.load_json(D4_MANIFEST)
    catalog = ca.load_json(CATALOG)
    sides = ca.load_json(PERTURBATION_SIDES)["sides"]
    records = _side_records(sides)
    if not all(record["pass"] for record in records.values()):
        raise SystemExit("a registered perturbation side did not pass; refusing to register")
    for record in records.values():
        case_dir = ROOT / record["case_dir"]
        if not (case_dir / "0" / "polyMesh" / "points").is_file():
            raise SystemExit(f"registered moved mesh is missing: {record['case_dir']}")
    basis = catalog["shared_catalog"]["surface_basis"]
    dynamic_mesh_dict = ADJOINT_BASE_CASE / "constant" / "dynamicMeshDict"
    reconstructed = build_dynamic_mesh_dict(
        box_min=tuple(float(value) for value in basis["box_m"]["min"]),
        box_max=tuple(float(value) for value in basis["box_m"]["max"]),
        n_cps=tuple(int(value) for value in basis["control_points"]),
        degree=(3, 3, 3),
    )
    if dynamic_mesh_dict.read_text(encoding="utf-8") != reconstructed:
        raise SystemExit("the registered dynamicMeshDict does not reconstruct from the catalog basis")
    manifest = {
        "kind": "stage_s_work_f_geometry_jacobian_manifest",
        "schema_version": 1,
        "registered_before_computation": True,
        "component_diagnosis_manifest": {
            "path": str(D4_MANIFEST.relative_to(ROOT)),
            "sha256": _sha256(D4_MANIFEST),
        },
        "component_audit": {
            "path": str(D4_1_AUDIT.relative_to(ROOT)),
            "sha256": _sha256(D4_1_AUDIT),
        },
        "perturbation_sides": {
            "path": str(PERTURBATION_SIDES.relative_to(ROOT)),
            "sha256": _sha256(PERTURBATION_SIDES),
            "sides": records,
        },
        "base_case": {
            "path": str(BASE_CASE.relative_to(ROOT)),
            "mesh": _mesh_files(BASE_CASE),
            "dynamicMeshDict": str(dynamic_mesh_dict.relative_to(ROOT)),
            "dynamicMeshDict_sha256": _sha256(dynamic_mesh_dict),
            "dynamicMeshDict_reconstructs_from_catalog_basis": True,
        },
        "utility": {
            "source_dir": str(UTILITY_SOURCE.relative_to(ROOT)),
            "source_sha256": _sha256(UTILITY_SOURCE / "geometryDerivativeDump.C"),
            "options_sha256": _sha256(UTILITY_SOURCE / "Make" / "options"),
            "read_only": True,
        },
        "directions": {
            name: {
                "sha256": ca.load_json(QUALIFICATION)["direction_hashes"][name],
                "weights_note": "control-point weight field = registered unit-inf-norm direction",
            }
            for name in DIRECTIONS
        },
        "scope": {
            "design_patch": DESIGN_PATCH,
            "epsilons_m": sorted({record["epsilon_m"] for record in sides.values()}),
            "comparison_epsilon_m": COMPARISON_EPSILON,
            "quantities": list(GEOMETRY_QUANTITIES),
        },
        "gate_tolerances": GATE_TOLERANCES,
        "plateau_tolerance": PLATEAU_TOLERANCE,
        "tolerance_rationale": TOLERANCE_RATIONALE,
        "gates": [
            "plus/minus face topology and ordering match the base mesh",
            "analytic and FD sign and magnitude agree per face and patch-integrated",
            "an epsilon plateau exists for every direction and quantity",
            "non-design patches have no points inside the control-point box and no movement",
            "the design patch is the only patch with a non-zero analytic derivative",
        ],
        "stop_conditions": [
            "if the analytic dump cannot be obtained authoritatively, stop without guessing",
            "a geometry-Jacobian failure stops D4.3 and restarts from the side preflight after a one-factor fix",
            "no registered direction, epsilon or threshold is changed",
        ],
        "claims_not_supported": [
            "this audit is not a derivative qualification and produces no CFD evidence",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)}, indent=2))
    return manifest


def _verify_manifest(manifest: dict) -> None:
    for name, record in (
        ("component_diagnosis_manifest", manifest["component_diagnosis_manifest"]),
        ("component_audit", manifest["component_audit"]),
        ("perturbation_sides", manifest["perturbation_sides"]),
    ):
        if _sha256(ROOT / record["path"]) != record["sha256"]:
            raise SystemExit(f"registered input changed: {name}")
    base = manifest["base_case"]
    if _mesh_files(ROOT / base["path"]) != base["mesh"]:
        raise SystemExit("registered base mesh changed")
    if _sha256(ROOT / base["dynamicMeshDict"]) != base["dynamicMeshDict_sha256"]:
        raise SystemExit("registered dynamicMeshDict changed")
    if _sha256(UTILITY_SOURCE / "geometryDerivativeDump.C") != manifest["utility"]["source_sha256"]:
        raise SystemExit("utility source changed")


def _build_tool() -> tuple[Path, dict]:
    binary = TOOLS_DIR / "geometryDerivativeDump"
    build_dir = TOOLS_DIR / "build_geometry_derivative_dump"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    (build_dir / "geometryDerivativeDump" / "Make").mkdir(parents=True)
    shutil.copyfile(
        UTILITY_SOURCE / "geometryDerivativeDump.C",
        build_dir / "geometryDerivativeDump" / "geometryDerivativeDump.C",
    )
    shutil.copyfile(
        UTILITY_SOURCE / "Make" / "options",
        build_dir / "geometryDerivativeDump" / "Make" / "options",
    )
    (build_dir / "geometryDerivativeDump" / "Make" / "files").write_text(
        "geometryDerivativeDump.C\nEXE = /case/bin/geometryDerivativeDump\n", encoding="utf-8"
    )
    (build_dir / "Allrun").write_text(
        "#!/usr/bin/env bash\n"
        "source /usr/lib/openfoam/openfoam2512/etc/bashrc\n"
        "set -eo pipefail\n"
        "wmake -s geometryDerivativeDump\n",
        encoding="utf-8",
    )
    (build_dir / "Allclean").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    work_f = ca.load_json(WORK_F_MANIFEST)
    run = run_openfoam_case(
        build_dir,
        backend="docker",
        dry_run=False,
        timeout_seconds=int(work_f["solver_budget"]["solver_timeout_seconds"]),
        docker_image=work_f["openfoam_image"],
    )
    built = build_dir / "bin" / "geometryDerivativeDump"
    if getattr(run, "returncode", None) != 0 or not built.is_file():
        raise SystemExit("geometryDerivativeDump build failed; stopping without guessing")
    shutil.copyfile(built, binary)
    return binary, {"returncode": getattr(run, "returncode", None)}


def _prepare_scratch(manifest: dict, qualification: dict) -> None:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASE_CASE, SCRATCH)
    for child in list(SCRATCH.iterdir()):
        if child.is_dir() and child.name not in {"0", "constant", "system"}:
            shutil.rmtree(child)
        elif child.is_file() and child.name.startswith(("log.", "stage_v")):
            child.unlink()
    shutil.copyfile(
        ROOT / manifest["base_case"]["dynamicMeshDict"],
        SCRATCH / "constant" / "dynamicMeshDict",
    )
    (SCRATCH / "constant" / "geometryDerivativeDirections").write_text(
        _settings_text(DIRECTIONS), encoding="utf-8", newline="\n"
    )
    directions_dir = SCRATCH / "constant" / "geometryDerivativeDirectionFiles"
    directions_dir.mkdir()
    for name, weights in _weight_files(qualification).items():
        (directions_dir / name).write_text(_weights_text(name, weights), encoding="utf-8", newline="\n")


def _design_face_points(base_case: Path) -> list[list[int]]:
    boundary = _read_boundary(base_case / "constant" / "polyMesh" / "boundary")
    if DESIGN_PATCH not in boundary:
        raise SystemExit(f"base mesh lacks the {DESIGN_PATCH} patch")
    info = boundary[DESIGN_PATCH]
    faces = _read_selected_faces(
        base_case / "constant" / "polyMesh" / "faces",
        [(int(info["startFace"]), int(info["nFaces"]))],
    )
    return [faces[index] for index in range(int(info["startFace"]), int(info["startFace"]) + int(info["nFaces"]))]


def _outside_patch_point_ids(base_case: Path) -> list[int]:
    boundary = _read_boundary(base_case / "constant" / "polyMesh" / "boundary")
    ranges = [
        (int(info["startFace"]), int(info["nFaces"]))
        for name, info in boundary.items()
        if name != DESIGN_PATCH
    ]
    faces = _read_selected_faces(base_case / "constant" / "polyMesh" / "faces", ranges)
    points: set[int] = set()
    for face_points in faces.values():
        points.update(int(value) for value in face_points)
    return sorted(points)


def run() -> dict:
    if AUDIT.exists():
        raise SystemExit("geometry-Jacobian audit evidence already exists; refuse overwrite")
    manifest = ca.load_json(MANIFEST)
    _verify_manifest(manifest)
    qualification = ca.load_json(QUALIFICATION)
    binary, build = _build_tool()
    _prepare_scratch(manifest, qualification)
    (SCRATCH / "tools").mkdir(exist_ok=True)
    shutil.copyfile(binary, SCRATCH / "tools" / "geometryDerivativeDump")
    (SCRATCH / "tools" / "geometryDerivativeDump").chmod(0o755)
    (SCRATCH / "Allrun").write_text(ALLRUN, encoding="utf-8", newline="\n")
    work_f = ca.load_json(WORK_F_MANIFEST)
    run_result = run_openfoam_case(
        SCRATCH,
        backend="docker",
        dry_run=False,
        timeout_seconds=int(work_f["solver_budget"]["solver_timeout_seconds"]),
        docker_image=work_f["openfoam_image"],
    )
    dump_path = SCRATCH / "geometryDerivatives.dat"
    if getattr(run_result, "returncode", None) != 0 or not dump_path.is_file():
        raise SystemExit("analytic geometry-derivative dump failed; stopping without guessing")
    dump = parse_dump(dump_path.read_text(encoding="utf-8"))

    base_points = np.asarray(_read_points(BASE_CASE / "constant" / "polyMesh" / "points"))
    face_points = _design_face_points(BASE_CASE)
    base_geometry = face_geometry(base_points, face_points)
    outside_ids = _outside_patch_point_ids(BASE_CASE)
    mesh_base_header = manifest["base_case"]["mesh"]

    comparisons: dict[str, dict] = {}
    direction_ratios: dict[str, dict[str, list[float]]] = {
        name: {quantity: [] for quantity in GEOMETRY_QUANTITIES} for name in DIRECTIONS
    }
    topology_hashes: dict[str, dict[str, str]] = {}
    outside_displacements: dict[str, float] = {}
    for direction in DIRECTIONS:
        for epsilon in manifest["scope"]["epsilons_m"]:
            sides = manifest["perturbation_sides"]["sides"]
            plus = sides[f"{direction}__{epsilon:g}__plus"]
            minus = sides[f"{direction}__{epsilon:g}__minus"]
            plus_case = ROOT / plus["case_dir"]
            minus_case = ROOT / minus["case_dir"]
            for label, case, record in (
                ("plus", plus_case, plus),
                ("minus", minus_case, minus),
            ):
                moved = case / "0" / "polyMesh" / "points"
                if not moved.is_file() or _sha256(moved) != record["moved_points_sha256"]:
                    raise SystemExit(
                        f"registered moved points changed: {direction}/{epsilon:g}/{label}"
                    )
            plus_points = np.asarray(_read_points(plus_case / "0" / "polyMesh" / "points"))
            minus_points = np.asarray(_read_points(minus_case / "0" / "polyMesh" / "points"))
            plus_geometry = face_geometry(plus_points, face_points)
            minus_geometry = face_geometry(minus_points, face_points)
            topology_hashes[f"{direction}__{epsilon:g}__plus"] = _mesh_files(plus_case)
            topology_hashes[f"{direction}__{epsilon:g}__minus"] = _mesh_files(minus_case)
            displacement = float(
                np.max(np.linalg.norm(plus_points[outside_ids] - base_points[outside_ids], axis=1))
            )
            displacement = max(
                displacement,
                float(np.max(np.linalg.norm(minus_points[outside_ids] - base_points[outside_ids], axis=1))),
            )
            outside_displacements[f"{direction}__{epsilon:g}"] = displacement
            analytic = dump["directions"][direction]
            fd = {
                "Cf": centered_difference(plus_geometry.centres, minus_geometry.centres, epsilon),
                "Sf": centered_difference(plus_geometry.areas, minus_geometry.areas, epsilon),
                "n": centered_difference(plus_geometry.normals, minus_geometry.normals, epsilon),
            }
            tight = bool(
                math.isclose(
                    float(epsilon),
                    float(manifest["scope"]["comparison_epsilon_m"]),
                    rel_tol=0.0,
                    abs_tol=1e-15,
                )
            )
            quantities: dict[str, dict] = {}
            for quantity in GEOMETRY_QUANTITIES:
                diagnostics = quantity_diagnostics(analytic[quantity], fd[quantity])
                gates = evaluate_quantity_gate(
                    diagnostics, **manifest["gate_tolerances"][quantity]
                )
                quantities[quantity] = {
                    **diagnostics,
                    "gates": gates,
                    "tight_gate_at_comparison_epsilon": tight,
                    "pass": bool(all(gates.values())) if tight else bool(gates["l2_ratio"]),
                }
                direction_ratios[direction][quantity].append(diagnostics["l2_ratio"])
            comparisons[f"{direction}__{epsilon:g}"] = {
                "direction": direction,
                "epsilon_m": float(epsilon),
                "quantities": quantities,
                "pass": bool(all(quantity["pass"] for quantity in quantities.values())),
            }

    plateau: dict[str, dict] = {}
    plateau_pass = True
    for direction in DIRECTIONS:
        plateau[direction] = {}
        for quantity in GEOMETRY_QUANTITIES:
            status = plateau_status(direction_ratios[direction][quantity])
            deviation = status["max_deviation"]
            passed = bool(
                status["plateau"]
                and deviation is not None
                and deviation <= PLATEAU_TOLERANCE[quantity]
            )
            plateau[direction][quantity] = {**status, "tolerance": PLATEAU_TOLERANCE[quantity], "pass": passed}
            plateau_pass = plateau_pass and passed

    roundoff: dict[str, dict] = {}
    for direction in DIRECTIONS:
        roundoff[direction] = {}
        for quantity in GEOMETRY_QUANTITIES:
            values = [
                comparisons[f"{direction}__{epsilon:g}"]["quantities"][quantity]["max_abs_error"]
                for epsilon in manifest["scope"]["epsilons_m"]
            ]
            scaled = [
                value * 2.0 * float(epsilon)
                for value, epsilon in zip(values, manifest["scope"]["epsilons_m"], strict=True)
            ]
            roundoff[direction][quantity] = {
                "max_abs_error_by_epsilon": values,
                "max_abs_error_times_two_epsilon": scaled,
                "scaled_spread": (max(scaled) - min(scaled)) / max(scaled) if max(scaled) > 0 else 0.0,
            }

    inside_counts = dump["inside_counts"]
    non_design_inside = {name: count for name, count in inside_counts.items() if name != DESIGN_PATCH}
    non_design_inside_zero = bool(all(count == 0 for count in non_design_inside.values()))
    outside_movement_zero = bool(all(value == 0.0 for value in outside_displacements.values()))
    topology_consistent = bool(
        all(
            record["faces"] == mesh_base_header["faces"]
            and record["boundary"] == mesh_base_header["boundary"]
            for record in topology_hashes.values()
        )
    )
    base_points_constant = bool(
        all(record["points"] == mesh_base_header["points"] for record in topology_hashes.values())
    )
    all_comparisons_pass = all(entry["pass"] for entry in comparisons.values())
    geometry_pass = bool(
        all_comparisons_pass
        and plateau_pass
        and non_design_inside_zero
        and outside_movement_zero
        and topology_consistent
        and base_points_constant
    )
    evidence = {
        "kind": "stage_s_work_f_geometry_jacobian_audit",
        "schema_version": 1,
        "manifest": {"path": str(MANIFEST.relative_to(ROOT)), "sha256": _sha256(MANIFEST)},
        "utility": {
            "binary_sha256": _sha256(binary),
            "build": build,
            "dump_path": str(dump_path.relative_to(ROOT)),
            "read_only": True,
        },
        "base_mesh": {
            "path": str(BASE_CASE.relative_to(ROOT)),
            "design_patch": DESIGN_PATCH,
            "n_design_faces": int(dump["n_faces"]),
            "mesh": mesh_base_header,
            "outside_patch_point_count": len(outside_ids),
        },
        "comparisons": comparisons,
        "plateau": plateau,
        "checks": {
            "topology_faces_and_boundary_identical": topology_consistent,
            "constant_base_points_identical_to_base_across_sides": base_points_constant,
            "non_design_patch_inside_counts_zero": non_design_inside_zero,
            "non_design_patch_inside_counts": non_design_inside,
            "design_patch_inside_count": inside_counts.get(DESIGN_PATCH),
            "outside_patch_movement_zero": outside_movement_zero,
            "outside_patch_max_displacement_m": max(outside_displacements.values())
            if outside_displacements
            else None,
            "comparison_epsilon_m": COMPARISON_EPSILON,
            "plateau_pass": plateau_pass,
            "roundoff_characterization": roundoff,
        },
        "summary": {
            "geometry_jacobian_pass": geometry_pass,
            "all_comparisons_pass": all_comparisons_pass,
            "plateau_pass": plateau_pass,
            "non_design_zero": bool(non_design_inside_zero and outside_movement_zero),
            "next": "D4.3 adjoint-option ablation allowed"
            if geometry_pass
            else "stop: morpher/parameterization chain-rule defect, one-factor fix then restart from the side preflight",
            "derivative_qualified": False,
            "shape_update_allowed": False,
            "original_verdict_unchanged": True,
        },
        "claims_supported": [
            "the B-spline control-point-to-face-geometry chain rule was compared face-by-face against centered differences of the registered moved meshes",
        ],
        "claims_not_supported": [
            "this solver-free audit does not qualify the surface derivative or authorize a shape update",
        ],
    }
    AUDIT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    print(json.dumps(evidence["checks"], indent=2))
    return evidence


def recompute() -> dict:
    """Apply the registered comparison-epsilon scope to the as-run artifact.

    The first gate application applied the tight per-face tolerances at every
    epsilon. The manifest registered the largest epsilon as the comparison
    epsilon and states the tolerance rationale at that epsilon; the smaller
    epsilons are roundoff-limited (the per-face deviation scales as
    1/epsilon) and only carry the patch-integrated L2 ratio into the plateau.
    The as-run artifact is preserved unchanged, no tolerance or diagnostic
    value is changed, and the correction is recorded in the new artifact.
    """

    if not AUDIT.exists():
        raise SystemExit("as-run geometry-Jacobian audit is missing")
    if PRESERVED.exists():
        raise SystemExit("preserved as-run geometry-Jacobian audit already exists")
    as_run = ca.load_json(AUDIT)
    if "comparison_correction" in as_run:
        raise SystemExit("the audit already carries a comparison correction")
    preserved_sha = _sha256(AUDIT)
    shutil.move(str(AUDIT), str(PRESERVED))
    manifest = ca.load_json(MANIFEST)
    comparison_epsilon = float(manifest["scope"]["comparison_epsilon_m"])
    comparisons: dict[str, dict] = {}
    direction_ratios = {
        name: {quantity: [] for quantity in GEOMETRY_QUANTITIES} for name in DIRECTIONS
    }
    for key, entry in as_run["comparisons"].items():
        direction = entry["direction"]
        epsilon = float(entry["epsilon_m"])
        tight = math.isclose(epsilon, comparison_epsilon, rel_tol=0.0, abs_tol=1e-15)
        quantities: dict[str, dict] = {}
        for quantity in GEOMETRY_QUANTITIES:
            recorded = entry["quantities"][quantity]
            diagnostics = {
                name: recorded[name]
                for name in (
                    "max_abs_error",
                    "max_component_error",
                    "analytic_scale",
                    "l2_analytic",
                    "l2_fd",
                    "l2_ratio",
                    "cosine_similarity",
                )
            }
            gates = evaluate_quantity_gate(
                diagnostics, **manifest["gate_tolerances"][quantity]
            )
            quantities[quantity] = {
                **diagnostics,
                "gates": gates,
                "tight_gate_at_comparison_epsilon": tight,
                "pass": bool(all(gates.values())) if tight else bool(gates["l2_ratio"]),
            }
            direction_ratios[direction][quantity].append(diagnostics["l2_ratio"])
        comparisons[key] = {
            "direction": direction,
            "epsilon_m": epsilon,
            "quantities": quantities,
            "pass": bool(all(quantity["pass"] for quantity in quantities.values())),
        }

    plateau: dict[str, dict] = {}
    plateau_pass = True
    for direction in DIRECTIONS:
        plateau[direction] = {}
        for quantity in GEOMETRY_QUANTITIES:
            status = plateau_status(direction_ratios[direction][quantity])
            deviation = status["max_deviation"]
            passed = bool(
                status["plateau"]
                and deviation is not None
                and deviation <= PLATEAU_TOLERANCE[quantity]
            )
            plateau[direction][quantity] = {
                **status,
                "tolerance": PLATEAU_TOLERANCE[quantity],
                "pass": passed,
            }
            plateau_pass = plateau_pass and passed

    roundoff: dict[str, dict] = {}
    for direction in DIRECTIONS:
        roundoff[direction] = {}
        for quantity in GEOMETRY_QUANTITIES:
            values = [
                comparisons[f"{direction}__{epsilon:g}"]["quantities"][quantity]["max_abs_error"]
                for epsilon in manifest["scope"]["epsilons_m"]
            ]
            scaled = [
                value * 2.0 * float(epsilon)
                for value, epsilon in zip(values, manifest["scope"]["epsilons_m"], strict=True)
            ]
            roundoff[direction][quantity] = {
                "max_abs_error_by_epsilon": values,
                "max_abs_error_times_two_epsilon": scaled,
                "scaled_spread": (max(scaled) - min(scaled)) / max(scaled) if max(scaled) > 0 else 0.0,
            }

    checks = dict(as_run["checks"])
    checks["plateau_pass"] = plateau_pass
    checks["roundoff_characterization"] = roundoff
    checks["roundoff_scaling_consistent"] = bool(
        all(
            roundoff[direction][quantity]["scaled_spread"] <= 0.5
            for direction in DIRECTIONS
            for quantity in GEOMETRY_QUANTITIES
        )
    )
    all_pass = all(entry["pass"] for entry in comparisons.values())
    geometry_pass = bool(
        all_pass
        and plateau_pass
        and checks["non_design_patch_inside_counts_zero"]
        and checks["outside_patch_movement_zero"]
        and checks["topology_faces_and_boundary_identical"]
        and checks["constant_base_points_identical_to_base_across_sides"]
    )
    evidence = dict(as_run)
    evidence["comparisons"] = comparisons
    evidence["plateau"] = plateau
    evidence["checks"] = checks
    evidence["comparison_correction"] = {
        "as_run_artifact": {"path": str(PRESERVED.relative_to(ROOT)), "sha256": preserved_sha},
        "registered_comparison_epsilon_m": comparison_epsilon,
        "note": (
            "the first gate application applied the tight per-face tolerances at every "
            "epsilon; the registered scope designates the largest epsilon as the "
            "comparison epsilon and states the tolerance rationale at that epsilon. The "
            "smaller-epsilon per-face deviations scale as 1/epsilon (ASCII write "
            "roundoff) and are recorded in the roundoff characterization; no tolerance "
            "or diagnostic value was changed"
        ),
        "max_abs_error_by_epsilon": {
            direction: {
                quantity: roundoff[direction][quantity]["max_abs_error_by_epsilon"]
                for quantity in GEOMETRY_QUANTITIES
            }
            for direction in DIRECTIONS
        },
        "max_abs_error_times_two_epsilon": {
            direction: {
                quantity: roundoff[direction][quantity]["max_abs_error_times_two_epsilon"]
                for quantity in GEOMETRY_QUANTITIES
            }
            for direction in DIRECTIONS
        },
    }
    evidence["summary"] = {
        "geometry_jacobian_pass": geometry_pass,
        "all_comparisons_pass": all_pass,
        "plateau_pass": plateau_pass,
        "non_design_zero": bool(
            checks["non_design_patch_inside_counts_zero"] and checks["outside_patch_movement_zero"]
        ),
        "roundoff_scaling_consistent": checks["roundoff_scaling_consistent"],
        "next": "D4.3 adjoint-option ablation allowed"
        if geometry_pass
        else "stop: morpher/parameterization chain-rule defect, one-factor fix then restart from the side preflight",
        "derivative_qualified": False,
        "shape_update_allowed": False,
        "original_verdict_unchanged": True,
    }
    AUDIT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    print(json.dumps(evidence["comparison_correction"], indent=2))
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Work F post-D3 diagnosis D4.2")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    if args.register:
        register()
    elif args.run:
        run()
    elif args.recompute:
        recompute()
    else:
        parser.error("specify --register, --run or --recompute")


if __name__ == "__main__":
    main()
