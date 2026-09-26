#!/usr/bin/env python3
"""Run S0R/S1R for the profile-aware Stage S reduced-basis contract.

The script runs only ``moveControlPoints`` and ``checkMesh`` in Docker.  It
never invokes simpleFoam/adjointOptimisationFoam and does not evaluate any
flow field.  The exact historical K=16 modes are reconstructed and hashed;
mode selection is not repeated.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import register_stage_s_reduced_basis_fd_v2_2026_09 as registration  # noqa: E402
from cfd_sdf import campaign_assertions as ca  # noqa: E402
from cfd_sdf.cfd import STAGE_V_QUALIFICATION_PROFILE_V1  # noqa: E402
from cfd_sdf.execution import run_openfoam_case  # noqa: E402
from cfd_sdf.stage_s_adjoint_case import build_dynamic_mesh_dict  # noqa: E402
from cfd_sdf.stage_s_perturbation import (  # noqa: E402
    extract_patch_surface,
    fixed_patch_immobility,
    movement_to_text,
    parse_check_mesh_qualified,
)
from cfd_sdf.extraction_qualification import _triangles_self_intersect  # noqa: E402
from cfd_sdf.handoff import _build_revoxelized_density  # noqa: E402
from cfd_sdf.shape_feature_metrics import occupancy_metrics  # noqa: E402
from cfd_sdf.stage_v_domain_preflight import (  # noqa: E402
    STAGE_V_CLEARANCE_PROFILE_V1,
    evaluate_stage_v_domain_preflight,
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
    ModeCandidate,
    canonical_sign,
    mode_sha256,
    mode_to_movement,
    normal_displacement,
    sine_mode_vector,
)

MANIFEST = registration.MANIFEST
EVIDENCE = registration.PREFLIGHT
BASE_CASE = registration.BASE_CASE
MORPHER = registration.MORPHER
SCRATCH_ROOT = ROOT / "work/stage_s_reduced_basis_fd_v2_2026_09/s0r_s1r"
ALLRUN = "#!/usr/bin/env bash\nset -euo pipefail\ntools/moveControlPoints | tee log.moveControlPoints\ncheckMesh -allGeometry -allTopology | tee log.checkMesh\n"
ALLRUN_CALIBRATION = "#!/usr/bin/env bash\nset -euo pipefail\ntools/moveControlPoints | tee log.moveControlPoints\n"


def _fast_surface_geometry_checks(
    *, baseline, moved, spec, minimum_width_reference_m: float | None = None
) -> dict[str, Any]:
    """Run the same geometry gates on a tight local voxel box.

    The registered domain is needed for clearance, but minimum-width
    revoxelization only depends on the candidate surface.  Using a one-cell
    padded bounding box avoids evaluating signed distance over all ~172k v2
    domain cells for every perturbation while preserving the metric and its
    0.05 m resolution.
    """

    moved_mesh = trimesh.Trimesh(vertices=moved.vertices, faces=moved.faces, process=True)
    baseline_mesh = trimesh.Trimesh(vertices=baseline.vertices, faces=baseline.faces, process=True)
    checks: dict[str, Any] = {
        "watertight": bool(moved_mesh.is_watertight),
        "winding_consistent": bool(moved_mesh.is_winding_consistent),
        "positive_volume": bool(moved_mesh.volume > 0.0),
        "self_intersection": _triangles_self_intersect(moved_mesh),
        "volume_m3": float(moved_mesh.volume),
        "baseline_volume_m3": float(baseline_mesh.volume),
        "volume_relative_difference": float(
            abs(moved_mesh.volume - baseline_mesh.volume) / max(abs(baseline_mesh.volume), 1e-30)
        ),
    }
    spacing = float(spec.grid.voxel_size_m)
    max_surface_displacement = float(
        np.linalg.norm(moved.vertices - baseline.vertices, axis=1).max()
    )
    if minimum_width_reference_m is None:
        lower = np.floor(np.asarray(moved_mesh.bounds[0], dtype=np.float64) / spacing) * spacing - spacing
        upper = np.ceil(np.asarray(moved_mesh.bounds[1], dtype=np.float64) / spacing) * spacing + spacing
        shape = tuple(int(np.ceil((upper[i] - lower[i]) / spacing)) for i in range(3))
        from cfd_sdf.fixed_grid_contract import CartesianCellGrid

        tight_grid = CartesianCellGrid(origin=tuple(lower), spacing=(spacing,) * 3, cell_shape=shape)
        revoxelized = _build_revoxelized_density(moved_mesh, tight_grid)
        metrics = occupancy_metrics(revoxelized.reshape(shape, order="F"), spacing)
        checks["minimum_solid_width_m"] = metrics.get("thickness_ridge_m_min")
        checks["minimum_width_grid"] = {
            "origin": list(lower),
            "cell_shape": list(shape),
            "spacing_m": spacing,
        }
        checks["minimum_width_method"] = "tight_bbox_revoxelized_occupancy"
    else:
        # Every point moves by at most delta, so any two opposing surfaces can
        # approach by at most 2*delta.  This is a conservative lower bound on
        # the registered baseline width and avoids repeating the expensive
        # signed-distance query for every side.
        checks["minimum_solid_width_m"] = max(
            float(minimum_width_reference_m) - 2.0 * max_surface_displacement, 0.0
        )
        checks["minimum_width_reference_m"] = float(minimum_width_reference_m)
        checks["minimum_width_max_surface_displacement_m"] = max_surface_displacement
        checks["minimum_width_method"] = "baseline_width_minus_two_sup_norm_displacement"
    with tempfile.TemporaryDirectory(prefix="stage_s_v2_geometry_") as tmp:
        stl_path = Path(tmp) / "moved.stl"
        moved_mesh.export(stl_path)
        clearance = evaluate_stage_v_domain_preflight(
            spec, stl_path, spacing, profile=STAGE_V_CLEARANCE_PROFILE_V1
        )
    checks["clearance_qualified"] = bool(clearance.qualified)
    checks["clearance_reasons"] = list(clearance.reasons)
    checks["pass"] = bool(
        checks["watertight"]
        and checks["winding_consistent"]
        and checks["positive_volume"]
        and checks["self_intersection"] == "none"
        and checks["clearance_qualified"]
    )
    return checks


def _sha256(path: Path) -> str:
    return ca.sha256_file(path)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_immutable(path: Path, document: dict[str, Any]) -> str:
    payload = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise SystemExit(f"refusing to overwrite immutable artifact: {_rel(path)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(payload, encoding="utf-8", newline="\n")
    digest = _sha256(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.exists() and sidecar.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit(f"preflight sidecar mismatch: {_rel(sidecar)}")
    if not sidecar.exists():
        sidecar.write_text(digest + "\n", encoding="utf-8", newline="\n")
    return digest


def _verify_contract() -> dict[str, Any]:
    registration.verify()
    manifest = _load(MANIFEST)
    if manifest["execution"]["solver_started"] or manifest["flags"]["solver_campaign_started"]:
        raise SystemExit("registered contract already reports a solver campaign")
    if EVIDENCE.exists():
        raise SystemExit("S0R/S1R evidence already exists; refuse a second preflight")
    if not BASE_CASE.is_dir():
        raise SystemExit("the registered v2 body-fitted source case is missing")
    return manifest


def _reset_case(case_dir: Path) -> None:
    if case_dir.exists():
        raise SystemExit(f"refusing to overwrite an existing S0R/S1R case: {_rel(case_dir)}")
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASE_CASE, case_dir)
    # Keep the immutable v2 mesh and the initial U/p fields, but never copy
    # completed solver times, force histories, or prior dynamic-mesh output.
    for child in list(case_dir.iterdir()):
        if child.name in {"0", "constant", "system"}:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    time0 = case_dir / "0"
    for child in list(time0.iterdir()):
        if child.name not in {"U", "p"}:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    for relative in ("constant/dynamicMeshDict", "constant/controlPointsMovement", "0/polyMesh", "0/uniform", "tools"):
        path = case_dir / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
    # ``run_openfoam_case`` keeps the standard wrapper contract and invokes
    # ``Allclean`` even for this mesh-only command.  The source Stage V case
    # may not carry that helper, so provide an inert local cleanup script.
    (case_dir / "Allclean").write_text("#!/usr/bin/env bash\nset -euo pipefail\n", encoding="utf-8", newline="\n")


def _prepare_case(
    case_dir: Path, movement: np.ndarray, basis: dict[str, Any], *, allrun: str = ALLRUN
) -> None:
    _reset_case(case_dir)
    (case_dir / "constant/dynamicMeshDict").write_text(
        build_dynamic_mesh_dict(
            box_min=tuple(float(v) for v in basis["box_m"]["min"]),
            box_max=tuple(float(v) for v in basis["box_m"]["max"]),
            n_cps=tuple(int(v) for v in basis["control_points"]),
            degree=(3, 3, 3),
        ),
        encoding="utf-8",
        newline="\n",
    )
    (case_dir / "constant/controlPointsMovement").write_text(
        movement_to_text(movement), encoding="utf-8", newline="\n"
    )
    tools = case_dir / "tools"
    tools.mkdir()
    shutil.copyfile(MORPHER, tools / "moveControlPoints")
    (tools / "moveControlPoints").chmod(0o755)
    (case_dir / "Allrun").write_text(allrun, encoding="utf-8", newline="\n")


def _run(case_dir: Path, timeout: int, image: str) -> dict[str, Any]:
    result = run_openfoam_case(
        case_dir,
        backend="docker",
        dry_run=False,
        timeout_seconds=timeout,
        docker_image=image,
    )
    return {
        "returncode": getattr(result, "returncode", None),
        "timed_out": getattr(result, "timed_out", None),
        "error": getattr(result, "error", None),
        "summary_path": _rel(result.summary_path),
        "summary_sha256": _sha256(result.summary_path) if result.summary_path.is_file() else None,
    }


def _base_checks(manifest: dict[str, Any]) -> dict[str, Any]:
    metadata_path = BASE_CASE / "case_metadata.json"
    metadata = _load(metadata_path)
    expected = manifest["base_case"]
    checks = {
        "metadata_sha256": _sha256(metadata_path) == next(
            ref["sha256"] for ref in expected["source_files"] if ref["path"].endswith("case_metadata.json")
        ),
        "problem_id": metadata.get("problem_id") == expected["problem_id"],
        "problem_spec_sha256": metadata.get("problem_spec_sha256") == expected["problem_spec_sha256"],
        "physical_profile_sha256": metadata.get("physical_profile", {}).get("sha256") == expected["physical_profile_sha256"],
        "candidate_sha256": _sha256(BASE_CASE / "constant/triSurface/design_candidate.stl") == manifest["candidate"]["sha256"],
        "poly_mesh_present": (BASE_CASE / "constant/polyMesh/boundary").is_file() and (BASE_CASE / "constant/polyMesh/faces").is_file(),
        "initial_fields_present": (BASE_CASE / "0/U").is_file() and (BASE_CASE / "0/p").is_file(),
    }
    bounds = metadata.get("grid", {}).get("bounds")
    expected_bounds = expected["domain_bounds_m"]
    checks["domain_bounds"] = bool(
        bounds
        and all(
            abs(float(bounds[i][j]) - float(expected_bounds["lower" if i == 0 else "upper"][j])) <= 1.0e-9
            for i in range(2)
            for j in range(3)
        )
    )
    checks["pass"] = all(value for key, value in checks.items() if key != "pass")
    return {"checks": checks, "metadata": metadata}


def _mode_from_record(record: dict[str, Any], active_ids: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    candidate = record["candidate"]
    mode = ModeCandidate(a=int(candidate["a"]), b=int(candidate["b"]), c=int(candidate["c"]), axis=str(candidate["axis"]))
    raw, flipped = canonical_sign(sine_mode_vector(mode, active_ids=active_ids))
    # The historical JSON stores a rounded reciprocal factor.  The exact S1
    # vector was formed from the measured efficiency, so use that value to
    # preserve the original byte-level hash.
    normalized = raw / float(record["historical_normal_efficiency"])
    if mode_sha256(raw) != record["raw_vector_sha256"] or mode_sha256(normalized) != record["normalized_vector_sha256"]:
        raise SystemExit(f"historical mode hash mismatch during preflight: {mode.name}")
    if bool(flipped) != bool(record.get("sign_flipped", False)):
        raise SystemExit(f"historical mode sign mismatch during preflight: {mode.name}")
    return mode, normalized


def _side_record(
    *,
    mode_name: str,
    sign_label: str,
    case_dir: Path,
    run_record: dict[str, Any],
    baseline_patch,
    baseline_points: Path,
    base_cp: np.ndarray,
    active_mask: np.ndarray,
    normalized: np.ndarray,
    active_ids: tuple[int, ...],
    spec,
    grid,
    epsilon: float,
    minimum_width_reference_m: float,
) -> dict[str, Any]:
    moved = extract_patch_surface(case_dir, time_name="0")
    displacement = normal_displacement(
        base_vertices=baseline_patch.vertices, faces=baseline_patch.faces, moved_vertices=moved.vertices
    )
    realized = read_control_points_file(case_dir / "0/uniform/volumetricBSplines/boxcpsBsplines")
    prescribed = read_movement_file(case_dir / "constant/controlPointsMovement")
    realized_checks = audit_case(base=base_cp, realized=realized, prescribed=prescribed, active_mask=active_mask)
    check_log = case_dir / "log.checkMesh"
    check_mesh = parse_check_mesh_qualified(
        check_log.read_text(encoding="utf-8", errors="replace") if check_log.is_file() else "",
        profile=STAGE_V_QUALIFICATION_PROFILE_V1,
    )
    geometry = _fast_surface_geometry_checks(
        baseline=baseline_patch,
        moved=moved,
        spec=spec,
        minimum_width_reference_m=minimum_width_reference_m,
    )
    geometry["minimum_solid_width_threshold_m"] = 0.01
    geometry["minimum_solid_width_pass"] = bool(
        geometry.get("minimum_solid_width_m") is not None
        and float(geometry["minimum_solid_width_m"]) >= 0.01
    )
    geometry["volume_relative_difference_threshold"] = 0.02
    geometry["volume_relative_difference_pass"] = bool(
        float(geometry.get("volume_relative_difference", float("inf"))) <= 0.02
    )
    geometry["pass"] = bool(
        geometry.get("pass")
        and geometry["minimum_solid_width_pass"]
        and geometry["volume_relative_difference_pass"]
    )
    immobility = fixed_patch_immobility(
        case_dir=case_dir,
        baseline_points=baseline_points,
        moved_points=case_dir / "0/polyMesh/points",
    )
    normalized_displacement = float(displacement["max_abs_normal_displacement_m"]) / epsilon
    normalized_ok = bool(abs(normalized_displacement - 1.0) <= 1.0e-5)
    side_pass = bool(
        run_record["returncode"] == 0
        and not run_record["timed_out"]
        and check_mesh.get("qualified")
        and geometry.get("pass")
        and immobility.get("pass")
        and realized_checks.get("realized_equals_prescribed")
        and realized_checks.get("boundary_fixed")
        and realized_checks.get("inactive_zero")
        and normalized_ok
    )
    return {
        "mode": mode_name,
        "sign": sign_label,
        "case_dir": _rel(case_dir),
        "run": run_record,
        "morpher_success": bool(run_record["returncode"] == 0 and not run_record["timed_out"]),
        "check_mesh": check_mesh,
        "geometry": geometry,
        "immobility": immobility,
        "realized": {
            "realized_equals_prescribed": bool(realized_checks["realized_equals_prescribed"]),
            "boundary_fixed": bool(realized_checks["boundary_fixed"]),
            "inactive_zero": bool(realized_checks["inactive_zero"]),
            "max_abs_difference": float(realized_checks.get("max_realized_minus_prescribed_m", 0.0)),
        },
        "max_abs_normal_displacement_m": float(displacement["max_abs_normal_displacement_m"]),
        "normalized_displacement": normalized_displacement,
        "normalized_displacement_pass": normalized_ok,
        "pass": side_pass,
    }, realized


def preflight() -> dict[str, Any]:
    manifest = _verify_contract()
    base = _base_checks(manifest)
    if not base["checks"]["pass"]:
        raise SystemExit(f"S0R base case construction gate failed: {base['checks']}")
    from cfd_sdf.fixed_grid_contract import CartesianCellGrid
    from cfd_sdf.problem_spec import load_problem_spec

    spec = load_problem_spec(ROOT / manifest["stage_s_problem_spec"]["stage_s"]["path"])
    bounds = spec.grid.domain_bounds_m
    grid = CartesianCellGrid(
        origin=tuple(bounds.lower),
        spacing=(float(spec.grid.voxel_size_m),) * 3,
        cell_shape=tuple(int(round((float(bounds.upper[i]) - float(bounds.lower[i])) / float(spec.grid.voxel_size_m))) for i in range(3)),
    )
    old_s1 = _load(ROOT / manifest["source_artifacts"]["old_s1_evidence"]["path"])
    qualification = _load(ROOT / manifest["source_artifacts"]["old_qualification"]["path"])
    active_ids = tuple(int(value) for value in qualification["derivative_contract"]["active_var_ids"])
    active_mask = active_mask_from_ids(active_ids)
    base_cp = read_control_points_csv(ROOT / manifest["mode_basis"]["control_point_catalog"]["path"])
    baseline_patch = extract_patch_surface(BASE_CASE, time_name="constant")
    baseline_points = BASE_CASE / "constant/polyMesh/points"
    baseline_geometry = _fast_surface_geometry_checks(
        baseline=baseline_patch, moved=baseline_patch, spec=spec
    )
    if baseline_geometry.get("minimum_solid_width_m") is None:
        raise SystemExit("baseline v2 minimum-width measurement is unavailable")
    minimum_width_reference_m = float(baseline_geometry["minimum_solid_width_m"])
    timeout = 3600
    basis = {
        "box_m": manifest["morpher"]["box_m"],
        "control_points": manifest["morpher"]["control_points"],
    }
    modes_out: list[dict[str, Any]] = []
    all_pass = True
    for record in manifest["mode_basis"]["modes"]:
        mode, normalized = _mode_from_record(record, active_ids)
        calibration_case = SCRATCH_ROOT / "modes" / f"{mode.name}__calibration"
        calibration_movement = mode_to_movement(
            normalized, active_ids=active_ids, coefficient=1.0e-3, sign=1.0
        )
        _prepare_case(calibration_case, calibration_movement, basis, allrun=ALLRUN_CALIBRATION)
        calibration_run = _run(calibration_case, timeout, registration.OPENFOAM_IMAGE)
        calibration_efficiency = None
        calibration_error = None
        if calibration_run["returncode"] == 0 and not calibration_run["timed_out"]:
            calibration_patch = extract_patch_surface(calibration_case, time_name="0")
            calibration_displacement = normal_displacement(
                base_vertices=baseline_patch.vertices,
                faces=baseline_patch.faces,
                moved_vertices=calibration_patch.vertices,
            )
            calibration_efficiency = float(
                calibration_displacement["max_abs_normal_displacement_m"] / 1.0e-3
            )
            if not np.isfinite(calibration_efficiency) or calibration_efficiency <= 0.0:
                calibration_error = "non_positive_or_non_finite_v2_morpher_efficiency"
        else:
            calibration_error = "v2_morpher_calibration_failed"
        if calibration_error is not None:
            modes_out.append(
                {
                    "order": record["order"],
                    "candidate": record["candidate"],
                    "normalized_vector_sha256": record["normalized_vector_sha256"],
                    "calibration": {
                        "case_dir": _rel(calibration_case),
                        "run": calibration_run,
                        "pass": False,
                        "error": calibration_error,
                    },
                    "sides": {},
                    "direction_pass": False,
                    "pass": False,
                }
            )
            all_pass = False
            break
        # The historical vector direction is immutable; this scalar is a
        # new-domain physical-amplitude calibration so epsilon remains a
        # maximum normal displacement in the v2 mesh.
        calibrated = normalized / float(calibration_efficiency)
        sides: dict[str, Any] = {}
        realized_by_sign: dict[str, np.ndarray] = {}
        for sign, label in ((1.0, "plus"), (-1.0, "minus")):
            case_dir = SCRATCH_ROOT / "modes" / f"{mode.name}__{label}"
            movement = mode_to_movement(calibrated, active_ids=active_ids, coefficient=1.0e-3, sign=sign)
            _prepare_case(case_dir, movement, basis)
            run_record = _run(case_dir, timeout, registration.OPENFOAM_IMAGE)
            side, realized = _side_record(
                mode_name=mode.name,
                sign_label=label,
                case_dir=case_dir,
                run_record=run_record,
                baseline_patch=baseline_patch,
                baseline_points=baseline_points,
                base_cp=base_cp,
                active_mask=active_mask,
                normalized=calibrated,
                active_ids=active_ids,
                spec=spec,
                grid=grid,
                epsilon=1.0e-3,
                minimum_width_reference_m=minimum_width_reference_m,
            )
            sides[label] = side
            realized_by_sign[label] = realized
            if not side["pass"]:
                all_pass = False
                break
        if "plus" in realized_by_sign and "minus" in realized_by_sign:
            pair = (realized_by_sign["plus"] - realized_by_sign["minus"]) / (2.0e-3)
            direction_cp = direction_to_cp_space(calibrated, active_ids)
            comparison = direction_comparison(direction_cp=direction_cp, delta_odd=pair, active_mask=active_mask)
            even_component = float(np.max(np.abs((realized_by_sign["plus"] + realized_by_sign["minus"]) / 2.0 - base_cp)))
            movement_difference_m = float(comparison["max_abs_difference"]) * 1.0e-3
            direction_pass = bool(
                comparison["cosine_ok"]
                and movement_difference_m <= DIRECTION_CP_ABS_TOLERANCE_M
                and even_component <= EVEN_COMPONENT_ABS_TOLERANCE_M
            )
        else:
            comparison = {"status": "not_evaluated_after_side_failure"}
            even_component = None
            movement_difference_m = None
            direction_pass = False
        mode_pass = bool(all(side.get("pass") for side in sides.values()) and direction_pass)
        modes_out.append(
            {
                "order": record["order"],
                "candidate": record["candidate"],
                "normalized_vector_sha256": record["normalized_vector_sha256"],
                "calibration": {
                    "case_dir": _rel(calibration_case),
                    "run": calibration_run,
                    "v2_normal_efficiency": float(calibration_efficiency),
                    "v2_amplitude_scale": float(1.0 / calibration_efficiency),
                    "physical_basis_direction_unchanged": True,
                },
                "case_dirs": {label: side["case_dir"] for label, side in sides.items()},
                "sides": sides,
                "realized_direction": comparison,
                "realized_movement_difference_m": movement_difference_m,
                "realized_even_component_m": even_component,
                "direction_pass": direction_pass,
                "pass": mode_pass,
            }
        )
        if not mode_pass:
            all_pass = False
            break
    evidence = {
        "kind": "stage_s_reduced_basis_fd_v2_preflight",
        "schema_version": 1,
        "immutable": True,
        "manifest": {"path": _rel(MANIFEST), "sha256": _sha256(MANIFEST)},
        "source_case": {"path": _rel(BASE_CASE), "metadata_sha256": _sha256(BASE_CASE / "case_metadata.json")},
        "s0r": {
            "solver_started": False,
            "flow_fields_evaluated": False,
            "base_case_construction": base,
            "baseline_geometry": baseline_geometry,
        },
        "s1r": {
            "basis_policy": "exact historical K=16 mode vectors; no response-dependent reselection",
            "maximum_epsilon_m": 1.0e-3,
            "modes_requested": len(manifest["mode_basis"]["modes"]),
            "modes_evaluated": len(modes_out),
            "modes": modes_out,
            "stopped_on_first_failure": len(modes_out) < len(manifest["mode_basis"]["modes"]),
        },
        "summary": {
            "preflight_pass": bool(all_pass and len(modes_out) == len(manifest["mode_basis"]["modes"])),
            "n_modes_passed": sum(bool(mode["pass"]) for mode in modes_out),
            "n_modes_requested": len(manifest["mode_basis"]["modes"]),
            "solver_started": False,
            "reduced_basis_fd_qualified": "pending",
            "shape_update_allowed": False,
            "flow_campaign_allowed": bool(all_pass and len(modes_out) == len(manifest["mode_basis"]["modes"])),
        },
        "claims_supported": [
            "the exact historical K=16 mode basis was rebound to the v2 qualified profile/domain and checked without a flow solver",
            "each evaluated side was judged by the registered morpher, geometry, clearance, direction, immobility, and checkMesh gates",
        ],
        "claims_not_supported": [
            "no primal flow response, FD derivative, S2 epsilon calibration, S4 holdout, or shape update",
            "no absolute or grid-independent downforce qualification",
        ],
        "commands": ["moveControlPoints", "checkMesh -allGeometry -allTopology"],
    }
    digest = _write_immutable(EVIDENCE, evidence)
    evidence["sha256"] = digest
    print(json.dumps(evidence["summary"], ensure_ascii=False, sort_keys=True))
    return evidence


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Stage S reduced-basis v2 S0R/S1R solver-free preflight")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if not args.preflight:
        parser.error("specify --preflight")
    preflight()


if __name__ == "__main__":
    main()
