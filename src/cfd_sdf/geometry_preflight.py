"""Bounded, fail-closed geometry and resolution preflight for G3.

The report covers the declared SI/frame/grid contract, referenced STL mesh
metadata, and declared topology-policy lengths. It does not claim full G3
qualification: self-intersections, manufacturing targets, density-to-SDF
fidelity, and whole-domain voxel metrics remain unevaluated.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .problem_spec import ProblemSpec, load_problem_spec, problem_spec_sha256


GEOMETRY_PREFLIGHT_KIND = "cfd_g3_geometry_resolution_preflight"
GEOMETRY_PREFLIGHT_SCHEMA_VERSION = 1
_IMPLEMENTED = ("problem_spec", "si_units", "coordinate_frame", "grid", "geometry", "feature_resolution")
_UNIMPLEMENTED = ("self_intersection", "manufacturing_target", "density_to_sdf_fidelity", "whole_domain_voxelization")


def assess_geometry_preflight(
    problem: ProblemSpec | str | Path,
    minimum_cells_per_feature: int | float = 3,
) -> dict[str, Any]:
    """Assess the bounded G3 subset; a subset pass is not full qualification."""

    cells = _positive_float(minimum_cells_per_feature, "minimum_cells_per_feature")
    source = _source_path(problem)
    report = {
        "kind": GEOMETRY_PREFLIGHT_KIND,
        "schema_version": GEOMETRY_PREFLIGHT_SCHEMA_VERSION,
        "status": "fail",
        "minimum_cells_per_feature": cells,
        "scope": {
            "implemented_checks": list(_IMPLEMENTED),
            "unimplemented_checks": list(_UNIMPLEMENTED),
            "method": "STL mesh metadata plus declared topology-policy-to-grid ratios",
            "dense_domain_voxelization": False,
        },
        "problem": {
            "path": None if source is None else source.as_posix(),
            "source_sha256": _file_sha(source),
            "problem_id": None,
            "schema_version": None,
            "migrated": None,
            "problem_spec_sha256": None,
        },
        "checks": {},
        "geometry_regions": [],
        "qualification": {
            "status": "not_evaluated",
            "reason": "No valid problem specification was assessed yet.",
        },
        "reasons": [],
    }
    try:
        spec = problem if isinstance(problem, ProblemSpec) else load_problem_spec(problem)
    except Exception as exc:
        reason = f"problem_spec_invalid:{type(exc).__name__}:{exc}"
        report["checks"]["problem_spec"] = {"status": "fail", "reasons": [reason]}
        report["status"] = "fail"
        report["qualification"] = {"status": "fail", "reason": "The problem specification could not be parsed."}
        report["reasons"] = [reason]
        return _safe(report)

    report["problem"].update(
        {
            "problem_id": spec.problem_id,
            "schema_version": int(spec.schema_version),
            "migrated": bool(spec.migration.migrated),
            "problem_spec_sha256": _spec_sha(spec),
        }
    )
    checks = report["checks"]
    checks["problem_spec"] = {
        "status": "pass",
        "problem_id": spec.problem_id,
        "schema_version": int(spec.schema_version),
        "migrated": bool(spec.migration.migrated),
        "reasons": [],
    }
    checks.update(
        {
            "si_units": _units(spec),
            "coordinate_frame": _frame(spec),
            "grid": _grid(spec),
        }
    )
    geometry, regions = _geometry(spec)
    checks["geometry"] = geometry
    checks["feature_resolution"] = _features(spec, cells)
    for name, reason in {
        "self_intersection": "Self-intersection detection is outside this bounded G3 subset.",
        "manufacturing_target": "Manufacturing target qualification is outside this bounded G3 subset.",
        "density_to_sdf_fidelity": "Density-to-SDF fidelity metrics are outside this bounded G3 subset.",
        "whole_domain_voxelization": "Whole-domain voxelization and mask metrics are intentionally not run.",
    }.items():
        checks[name] = {"status": "not_implemented", "reasons": [reason]}
    report["geometry_regions"] = regions

    subset = tuple(checks[name] for name in _IMPLEMENTED)
    status = _aggregate(subset)
    report["status"] = status
    report["qualification"] = {
        "status": "fail" if status == "fail" else "not_evaluated",
        "reason": "At least one implemented G3 subset check failed."
        if status == "fail"
        else "The bounded subset passed or was incomplete; full G3 remains unevaluated.",
    }
    report["reasons"] = _reasons(subset)
    return _safe(report)


def _source_path(problem: ProblemSpec | str | Path) -> Path | None:
    return Path(problem.path).resolve() if isinstance(problem, ProblemSpec) else Path(problem).resolve() if isinstance(problem, (str, Path)) else None


def _positive_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _units(spec: ProblemSpec) -> dict[str, Any]:
    declared = {"length": str(spec.units.length), "time": str(spec.units.time), "mass": str(spec.units.mass)}
    expected = {"length": "m", "time": "s", "mass": "kg"}
    reasons = [] if declared == expected else ["units_must_be_si_base_units"]
    return {"status": "pass" if not reasons else "fail", "declared": declared, "expected": expected, "reasons": reasons}


def _frame(spec: ProblemSpec) -> dict[str, Any]:
    frame = spec.coordinate_frame
    try:
        origin = np.asarray(frame.origin_m, dtype=float)
        basis = np.asarray([frame.basis.x, frame.basis.y, frame.basis.z], dtype=float)
    except (TypeError, ValueError):
        return {"status": "fail", "frame_id": str(frame.id), "reasons": ["coordinate_frame_values_are_not_numeric_vectors"]}
    reasons: list[str] = []
    valid_origin = origin.shape == (3,) and np.isfinite(origin).all()
    valid_basis = basis.shape == (3, 3) and np.isfinite(basis).all()
    if not valid_origin:
        reasons.append("coordinate_frame_origin_nonfinite_or_wrong_shape")
    if not valid_basis:
        reasons.append("coordinate_frame_basis_nonfinite_or_wrong_shape")
    result: dict[str, Any] = {"status": "fail", "frame_id": str(frame.id), "origin_m": _list(origin) if valid_origin else None, "reasons": reasons}
    if valid_basis:
        norms = np.linalg.norm(basis, axis=1)
        dots = {"xy": float(np.dot(basis[0], basis[1])), "xz": float(np.dot(basis[0], basis[2])), "yz": float(np.dot(basis[1], basis[2]))}
        determinant = float(np.dot(np.cross(basis[0], basis[1]), basis[2]))
        result.update({"basis": [_list(vector) for vector in basis], "basis_norms": _list(norms), "basis_pairwise_dots": dots, "basis_handedness_determinant": determinant})
        if not np.allclose(norms, 1, atol=1e-6, rtol=0):
            reasons.append("coordinate_frame_basis_not_unit")
        if any(abs(dot) > 1e-6 for dot in dots.values()):
            reasons.append("coordinate_frame_basis_not_orthogonal")
        if not isfinite(determinant) or determinant < 1 - 1e-6:
            reasons.append("coordinate_frame_basis_not_right_handed")
    result["status"] = "pass" if not reasons else "fail"
    return result


def _grid(spec: ProblemSpec) -> dict[str, Any]:
    grid = spec.grid
    reasons: list[str] = []
    voxel, padding = _finite(grid.voxel_size_m), _finite(grid.padding_m)
    if grid.kind != "uniform_cartesian":
        reasons.append("unsupported_grid_kind_for_bounded_g3")
    if voxel is None or voxel <= 0:
        reasons.append("grid_voxel_size_must_be_positive_and_finite")
    if padding is None or padding < 0:
        reasons.append("grid_padding_must_be_nonnegative_and_finite")
    result: dict[str, Any] = {"status": "fail", "kind": str(grid.kind), "voxel_size_m": voxel, "padding_m": padding, "domain_bounds_declared": grid.domain_bounds_m is not None, "reasons": reasons}
    bounds = grid.domain_bounds_m
    if bounds is not None:
        try:
            lower, upper = np.asarray(bounds.lower, dtype=float), np.asarray(bounds.upper, dtype=float)
            extents = upper - lower
            result["domain_bounds_m"] = {"lower": _list(lower), "upper": _list(upper), "extents": _list(extents)}
            if lower.shape != (3,) or upper.shape != (3,) or not np.isfinite(lower).all() or not np.isfinite(upper).all() or not np.all(extents > 0):
                reasons.append("grid_domain_bounds_m_invalid")
        except (TypeError, ValueError):
            reasons.append("grid_domain_bounds_m_invalid")
    result["status"] = "pass" if not reasons else "fail"
    return result


def _geometry(spec: ProblemSpec) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not spec.geometry_regions:
        return {"status": "fail", "region_count": 0, "regions": [], "reasons": ["no_geometry_regions"]}, []
    regions = [_region(spec, region) for region in spec.geometry_regions]
    reasons = [f"{item['id']}:{reason}" for item in regions for reason in item["reasons"]]
    return {"status": "pass" if not reasons else "fail", "region_count": len(regions), "regions": regions, "reasons": reasons}, regions


def _region(spec: ProblemSpec, region: Any) -> dict[str, Any]:
    relative = Path(region.file)
    path = spec.resolve(relative).resolve()
    item: dict[str, Any] = {"id": str(region.id), "role": str(region.role), "file": relative.as_posix(), "sha256": None, "status": "fail", "vertex_count": None, "face_count": None, "bounds_m": None, "signed_volume_m3": None, "winding_consistent": None, "watertight": None, "degenerate_face_count": None, "reasons": []}
    if not path.is_file():
        item["reasons"].append("missing_stl")
        return item
    try:
        payload = path.read_bytes()
        item["sha256"] = hashlib.sha256(payload).hexdigest()
        raw = trimesh.load_mesh(path, process=False)
    except OSError:
        item["reasons"].append("stl_unreadable")
        return item
    except Exception as exc:
        item["reasons"].append(f"invalid_stl:{type(exc).__name__}")
        return item
    if not isinstance(raw, trimesh.Trimesh):
        item["reasons"].append("stl_contains_scene_instead_of_one_mesh")
        return item
    try:
        vertices, faces = np.asarray(raw.vertices, dtype=float), np.asarray(raw.faces)
    except (TypeError, ValueError):
        item["reasons"].append("stl_vertices_or_faces_not_numeric")
        return item
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        item["reasons"].append("nonfinite_or_invalid_vertices")
    elif faces.ndim != 2 or faces.shape[1] != 3:
        item["reasons"].append("invalid_face_index_shape")
    elif not np.issubdtype(faces.dtype, np.integer):
        item["reasons"].append("face_indices_not_integer")
    elif len(vertices) == 0 or len(faces) == 0:
        item["reasons"].append("empty_stl")
    elif np.any(faces < 0) or np.any(faces >= len(vertices)):
        item["reasons"].append("face_index_out_of_bounds")
    if item["reasons"]:
        return item
    item.update({"vertex_count": int(len(vertices)), "face_count": int(len(faces))})
    lower, upper = vertices.min(axis=0), vertices.max(axis=0)
    item["bounds_m"] = {"lower": _list(lower), "upper": _list(upper), "extents": _list(upper - lower)}
    triangles = vertices[faces.astype(np.int64, copy=False)]
    areas = 0.5 * np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    scale = float(np.ptp(vertices, axis=0).max())
    degenerate = (~np.isfinite(areas) | (areas <= np.finfo(float).eps * max(scale * scale, np.finfo(float).tiny)) | (faces[:, 0] == faces[:, 1]) | (faces[:, 0] == faces[:, 2]) | (faces[:, 1] == faces[:, 2]))
    item["degenerate_face_count"] = int(np.count_nonzero(degenerate))
    if item["degenerate_face_count"]:
        item["reasons"].append("degenerate_faces")
        return item
    try:
        # ``validate=True`` calls trimesh.fix_normals(), which can repair an
        # invalid input before this gate observes its winding. Merge duplicate
        # STL vertices without changing face order or orientation.
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False, validate=False)
        mesh.merge_vertices()
        item.update({"watertight": bool(mesh.is_watertight), "winding_consistent": bool(mesh.is_winding_consistent), "signed_volume_m3": float(mesh.volume)})
    except Exception as exc:
        item["reasons"].append(f"invalid_stl_mesh_properties:{type(exc).__name__}")
        return item
    if not item["watertight"]:
        item["reasons"].append("not_watertight")
    if not item["winding_consistent"]:
        item["reasons"].append("inconsistent_winding")
    if item["signed_volume_m3"] is None or not isfinite(item["signed_volume_m3"]):
        item["reasons"].append("nonfinite_signed_volume")
    elif item["signed_volume_m3"] <= 0:
        item["reasons"].append("non_positive_signed_volume")
    item["status"] = "pass" if not item["reasons"] else "fail"
    return item


def _features(spec: ProblemSpec, cells: float) -> dict[str, Any]:
    policy = spec.topology_policy
    declared = (("minimum_solid_width_m", policy.minimum_solid_width_m, cells), ("minimum_void_width_m", policy.minimum_void_width_m, cells), ("minimum_gap_m", policy.minimum_gap_m, cells), ("erosion_radius_m", policy.erosion_radius_m, 1.0))
    voxel = _finite(spec.grid.voxel_size_m)
    if not any(value is not None for _, value, _ in declared):
        return {"status": "not_evaluated", "evaluated": False, "measurement_basis": "declared topology_policy values", "voxel_size_m": voxel, "features": [], "reasons": ["no_declared_feature_policy"]}
    features, reasons = [], []
    for name, value, required in declared:
        if value is None:
            continue
        length = _finite(value)
        feature: dict[str, Any] = {"name": name, "declared_m": length, "required_cells": required, "required_m": None if voxel is None else voxel * required, "represented_cells": None, "status": "fail", "reasons": []}
        if length is None or length <= 0:
            feature["reasons"].append("declared_length_must_be_positive_and_finite")
        elif voxel is None or voxel <= 0:
            feature["reasons"].append("grid_voxel_size_unavailable")
        elif spec.grid.kind != "uniform_cartesian":
            feature["reasons"].append("unsupported_grid_kind_for_resolution_ratio")
        else:
            represented = length / voxel
            feature["represented_cells"] = represented
            if represented + 1e-12 < required:
                feature["reasons"].append(f"{name}_subgrid:{represented:.12g}_cells<{required:.12g}")
        feature["status"] = "pass" if not feature["reasons"] else "fail"
        features.append(feature)
        reasons.extend(f"{name}:{reason}" for reason in feature["reasons"])
    return {"status": "pass" if not reasons else "fail", "evaluated": True, "measurement_basis": "declared topology_policy values", "voxel_size_m": voxel, "features": features, "reasons": reasons}


def _aggregate(checks: tuple[Mapping[str, Any], ...]) -> str:
    if any(check.get("status") == "fail" for check in checks):
        return "fail"
    return "not_evaluated" if any(check.get("status") == "not_evaluated" for check in checks) else "pass"


def _reasons(checks: tuple[Mapping[str, Any], ...]) -> list[str]:
    return [str(reason) for check in checks for reason in check.get("reasons", ())]


def _list(values: np.ndarray) -> list[float] | None:
    return [float(value) for value in values] if values.ndim == 1 and np.isfinite(values).all() else None


def _file_sha(path: Path | None) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path is not None and path.is_file() else None
    except OSError:
        return None


def _spec_sha(spec: ProblemSpec) -> str | None:
    try:
        return problem_spec_sha256(spec)
    except Exception:
        return None


def _safe(report: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(report), ensure_ascii=False, allow_nan=False))


__all__ = ["assess_geometry_preflight"]
