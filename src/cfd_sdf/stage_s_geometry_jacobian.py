"""Work F D4.2 B-spline geometry-Jacobian audit (solver-free).

Compares the OpenFOAM analytic B-spline geometry derivatives of the design
patch (``dxdbFace``, ``dSdb``, ``dndb`` contracted with the registered
direction weights) against centered differences of the plus/minus moved
meshes. The face geometry follows the exact OpenFOAM definitions
(``face::centre``: area-weighted centroid with the central fan decomposition;
``face::areaNormal``: half the summed triangle normals), so the comparison is
a linear-algebra identity check of the morpher chain rule. No flow solver and
no registered threshold is involved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

GEOMETRY_QUANTITIES: tuple[str, ...] = ("Cf", "Sf", "n")
VSMALL = 1.0e-300


class GeometryJacobianError(ValueError):
    """Fail-closed geometry-Jacobian contract violation."""


@dataclass(frozen=True)
class FaceGeometry:
    """Face centres, area vectors and unit normals of one mesh patch."""

    centres: np.ndarray
    areas: np.ndarray
    normals: np.ndarray


def face_geometry(points: np.ndarray, face_point_lists: list[list[int]]) -> FaceGeometry:
    """The OpenFOAM ``face::centre``/``face::areaNormal`` geometry per face."""

    vertices = np.asarray(points, dtype=np.float64)
    count = len(face_point_lists)
    centres = np.zeros((count, 3), dtype=np.float64)
    areas = np.zeros((count, 3), dtype=np.float64)
    normals = np.zeros((count, 3), dtype=np.float64)
    for index, face_points in enumerate(face_point_lists):
        p = vertices[np.asarray(face_points, dtype=np.int64)]
        if p.shape[0] == 3:
            area = 0.5 * np.cross(p[1] - p[0], p[2] - p[0])
            centre = (p[0] + p[1] + p[2]) / 3.0
        else:
            mean_point = p.mean(axis=0)
            sum_normal = np.zeros(3, dtype=np.float64)
            sum_area = 0.0
            sum_area_centre = np.zeros(3, dtype=np.float64)
            n_points = p.shape[0]
            for point_index in range(n_points):
                next_point = p[(point_index + 1) % n_points]
                triangle_normal = np.cross(next_point - p[point_index], mean_point - p[point_index])
                triangle_area = float(np.linalg.norm(triangle_normal))
                sum_normal += triangle_normal
                sum_area += triangle_area
                sum_area_centre += triangle_area * (p[point_index] + next_point + mean_point)
            area = 0.5 * sum_normal
            centre = sum_area_centre / (3.0 * sum_area) if sum_area > VSMALL else mean_point
        magnitude = float(np.linalg.norm(area))
        centres[index] = centre
        areas[index] = area
        normals[index] = area / magnitude if magnitude > VSMALL else 0.0
    return FaceGeometry(centres=centres, areas=areas, normals=normals)


def centered_difference(
    plus: np.ndarray, minus: np.ndarray, epsilon: float
) -> np.ndarray:
    if float(epsilon) <= 0.0:
        raise GeometryJacobianError("epsilon must be positive")
    return (np.asarray(plus, dtype=np.float64) - np.asarray(minus, dtype=np.float64)) / (
        2.0 * float(epsilon)
    )


def parse_dump(text: str) -> dict[str, Any]:
    """Parse the read-only ``geometryDerivatives.dat`` dump."""

    directions: dict[str, dict[str, np.ndarray]] = {}
    inside_counts: dict[str, int] = {}
    n_faces: int | None = None
    section: str | None = None
    current: str | None = None
    table: list[list[float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#direction "):
            current = stripped.split(None, 1)[1]
            directions[current] = {}
            continue
        if stripped.startswith("#n_design_faces "):
            n_faces = int(stripped.split()[1])
            continue
        if stripped.startswith("#face_table_begin "):
            section = "faces"
            table = []
            continue
        if stripped.startswith("#face_table_end "):
            section = None
            if current is None:
                raise GeometryJacobianError("face table without a direction")
            values = np.asarray(table, dtype=np.float64)
            if values.shape[1] != 10:
                raise GeometryJacobianError("malformed face table row")
            index = values[:, 0].astype(np.int64)
            if index.tolist() != list(range(values.shape[0])):
                raise GeometryJacobianError("face table indices are not consecutive")
            directions[current] = {
                "Cf": values[:, 1:4],
                "Sf": values[:, 4:7],
                "n": values[:, 7:10],
            }
            continue
        if stripped == "#patch_inside_counts_begin":
            section = "patches"
            continue
        if stripped == "#patch_inside_counts_end":
            section = None
            continue
        if section == "faces":
            table.append([float(part) for part in stripped.split()])
        elif section == "patches":
            name, count = stripped.split()
            inside_counts[name] = int(count)
    if n_faces is None:
        raise GeometryJacobianError("the dump lacks the design face count")
    for name, quantities in directions.items():
        for quantity in GEOMETRY_QUANTITIES:
            if quantities[quantity].shape != (n_faces, 3):
                raise GeometryJacobianError(f"{name}: {quantity} table has the wrong shape")
    return {"n_faces": n_faces, "directions": directions, "inside_counts": inside_counts}


def quantity_diagnostics(analytic: np.ndarray, fd: np.ndarray) -> dict[str, Any]:
    """Per-quantity error, scale, cosine and L2 ratio of analytic versus FD."""

    a = np.asarray(analytic, dtype=np.float64)
    f = np.asarray(fd, dtype=np.float64)
    if a.shape != f.shape:
        raise GeometryJacobianError("analytic and FD field shapes differ")
    error = f - a
    magnitudes = np.linalg.norm(f, axis=1)
    analytic_magnitudes = np.linalg.norm(a, axis=1)
    l2_analytic = float(math.sqrt(float(np.sum(analytic_magnitudes**2))))
    l2_fd = float(math.sqrt(float(np.sum(magnitudes**2))))
    denominator = float(math.sqrt(float(np.sum(analytic_magnitudes**2)))) * float(
        math.sqrt(float(np.sum(magnitudes**2)))
    )
    dot = float(np.sum(a * f))
    cosine = dot / denominator if denominator > VSMALL else 0.0
    return {
        "max_abs_error": float(np.max(np.linalg.norm(error, axis=1))),
        "max_component_error": float(np.max(np.abs(error))),
        "analytic_scale": float(np.max(analytic_magnitudes)),
        "l2_analytic": l2_analytic,
        "l2_fd": l2_fd,
        "l2_ratio": l2_fd / l2_analytic if l2_analytic > VSMALL else None,
        "cosine_similarity": cosine,
    }


def evaluate_quantity_gate(
    diagnostics: dict[str, Any], *, relative: float, absolute: float, l2_tolerance: float, cosine_min: float
) -> dict[str, bool]:
    l2_ratio = diagnostics["l2_ratio"]
    return {
        "max_error": bool(
            diagnostics["max_abs_error"]
            <= float(absolute) + float(relative) * diagnostics["analytic_scale"]
        ),
        "l2_ratio": bool(l2_ratio is not None and abs(l2_ratio - 1.0) <= float(l2_tolerance)),
        "cosine": bool(diagnostics["cosine_similarity"] >= float(cosine_min)),
    }


def plateau_status(ratios: list[float | None]) -> dict[str, Any]:
    values = [float(value) for value in ratios if value is not None]
    if len(values) < 2:
        return {"ratios": ratios, "max_deviation": None, "plateau": False}
    return {
        "ratios": ratios,
        "max_deviation": float(max(values) - min(values)),
        "plateau": True,
    }


__all__ = [
    "FaceGeometry",
    "GEOMETRY_QUANTITIES",
    "GeometryJacobianError",
    "centered_difference",
    "evaluate_quantity_gate",
    "face_geometry",
    "parse_dump",
    "plateau_status",
    "quantity_diagnostics",
]
