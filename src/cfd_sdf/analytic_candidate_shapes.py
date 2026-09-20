"""Pre-registered analytic binary shapes bounding occupancy and anchor STL together.

Implements the fixed-shape geometry set for the WP5/WP6 cross-fidelity ranking
program (`docs/problem_resolution_plan_2026_09.md` section 6.2 stage two): each
shape is defined analytically ONCE and produces BOTH (a) the exact binary voxel
occupancy on the canonical Stage T cell grid and (b) the watertight analytic
anchor STL for body-fitted Stage V, bound to one shared ``shape_id`` and SHA-256
file hashes. Because the anchor is analytic, the ranking is not contaminated by
iso-surface extraction error; extraction sensitivity is a separate declared
block against selected candidates.

Rotation convention: positive ``angle_y_deg`` rotates the body-frame +x (nose)
direction by a right-handed rotation about the global +y axis, mapping the nose
toward -z (nose down):

    world = R_y(ang) @ body + center, R_y = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

_SCHEMA_VERSION = 1

# Fixed canonical Stage T cell grid of the same-grid fixture (measured, not
# assumed): 60x32x24 cells, spacing 0.05 m, origin (-1.0, -0.8, -0.6),
# x-fastest order.
CANONICAL_SHAPE = (60, 32, 24)
CANONICAL_SPACING = 0.05
CANONICAL_ORIGIN = (-1.0, -0.8, -0.6)


@dataclass(frozen=True)
class ShapeDefinition:
    """One pre-registered analytic shape (immutable parameters).

    ``parts`` allows a composite shape: when non-empty it must be a tuple of
    single-box definitions, and the shape is the union of those boxes (one
    shared occupancy mask, one concatenated anchor STL). A composite part is
    ignored as an outer definition; only its box parameters are used.
    """

    shape_id: str
    chord_m: float
    span_m: float
    thickness_m: float
    angle_y_deg: float  # positive = nose down (see module docstring)
    center_m: tuple[float, float, float]
    parts: tuple["ShapeDefinition", ...] = ()


@dataclass(frozen=True)
class AnalyticShape:
    """One shape bound to its canonical-grid occupancy and anchor STL."""

    definition: ShapeDefinition
    occupancy: np.ndarray  # flat x-fastest bool of CANONICAL_SHAPE
    stl_bytes_sha256: str
    occupancy_npy_sha256: str

    @property
    def shape_id(self) -> str:
        return self.definition.shape_id


def shape_definitions() -> dict[str, ShapeDefinition]:
    """The pre-registered cross-fidelity ranking shape set.

    Ten shapes, one factor varied one at a time around the reference plate:
    an angle-of-attack series (nose-down 10/20/30 deg plus a nose-up control),
    a thickness series (0.05/0.10/0.15/0.25 m equivalent via the 30-deg entry),
    a half-span variant, a z-offset variant, and a bluff box. Registered before
    any run; no expected ranking is assumed.
    """

    center = (0.4, 0.05, 0.0)
    definitions = [
        ShapeDefinition("plate_a00_ref", 0.6, 0.8, 0.15, 0.0, center),
        ShapeDefinition("plate_a10_nd", 0.6, 0.8, 0.15, 10.0, center),
        ShapeDefinition("plate_a20_nd", 0.6, 0.8, 0.15, 20.0, center),
        ShapeDefinition("plate_a30_nd", 0.6, 0.8, 0.15, 30.0, center),
        ShapeDefinition("plate_a20_up", 0.6, 0.8, 0.15, -20.0, center),
        ShapeDefinition("plate_a20_t10", 0.6, 0.8, 0.10, 20.0, center),
        ShapeDefinition("plate_a20_t05", 0.6, 0.8, 0.05, 20.0, center),
        ShapeDefinition("plate_a20_span04", 0.6, 0.4, 0.15, 20.0, center),
        ShapeDefinition("plate_a20_zneg15", 0.6, 0.8, 0.15, 20.0, (0.4, 0.05, -0.15)),
        ShapeDefinition("box_bluff03", 0.3, 0.3, 0.3, 0.0, center),
    ]
    return {d.shape_id: d for d in definitions}


def reachable_set_definitions() -> dict[str, ShapeDefinition]:
    """Second pre-registered set (WP6-2): every shape has min solid thickness
    >= 0.15 m (3 cells at the T1 voxel), i.e. inside the project's registered
    minimum_solid_width policy space, and varies FSAE-relevant axes instead:
    camber-like bend, gurney edge, chord scale, two-element tandem, end plates,
    x-position, and same-thickness controls. Registered before any run.
    """

    base_center = (0.4, 0.05, 0.0)

    def part(chord, span, thickness, angle, center):
        return ShapeDefinition(
            f"part_{chord:g}_{span:g}_{thickness:g}_{angle:g}"
            f"_{center[0]:g}_{center[1]:g}_{center[2]:g}",
            chord, span, thickness, angle, center,
        )

    definitions = [
        ShapeDefinition(
            "wing_camber_bent", 0.0, 0.0, 0.0, 0.0, base_center,
            parts=(
                part(0.3, 0.8, 0.15, 30.0, (0.550, 0.05, 0.0785)),
                part(0.3, 0.8, 0.15, -10.0, (0.250, 0.05, -0.0785)),
            ),
        ),
        ShapeDefinition(
            "wing_gurney_a20", 0.0, 0.0, 0.0, 0.0, base_center,
            parts=(
                part(0.6, 0.8, 0.15, 20.0, base_center),
                part(0.05, 0.8, 0.12, 0.0, (0.3725, 0.05, 0.05)),
            ),
        ),
        ShapeDefinition("wing_chord03_a20", 0.3, 0.8, 0.15, 20.0, (0.4, 0.05, 0.0)),
        ShapeDefinition(
            "wing_two_element", 0.0, 0.0, 0.0, 0.0, base_center,
            parts=(
                part(0.3, 0.8, 0.15, 25.0, (0.250, 0.05, 0.0)),
                part(0.15, 0.8, 0.10, 35.0, (0.672, 0.05, -0.055)),
            ),
        ),
        ShapeDefinition(
            "wing_endplate_a20", 0.0, 0.0, 0.0, 0.0, base_center,
            parts=(
                part(0.6, 0.8, 0.15, 20.0, base_center),
                part(0.6, 0.05, 0.25, 20.0, (0.4, -0.425, 0.0)),
                part(0.6, 0.05, 0.25, 20.0, (0.4, 0.425, 0.0)),
            ),
        ),
        ShapeDefinition(
            "wing_tandem_xoff", 0.0, 0.0, 0.0, 0.0, base_center,
            parts=(
                part(0.3, 0.8, 0.15, 20.0, (0.25, 0.05, 0.0)),
                part(0.3, 0.8, 0.15, 40.0, (0.75, 0.05, 0.0)),
            ),
        ),
        ShapeDefinition("wing_flat_ctrl_c30", 0.3, 0.8, 0.25, 0.0, base_center),
        ShapeDefinition("wing_thick_a20", 0.6, 0.8, 0.25, 20.0, base_center),
    ]
    return {d.shape_id: d for d in definitions}


def _rotation_about_y(angle_deg: float) -> np.ndarray:
    rad = math.radians(angle_deg)
    s, c = math.sin(rad), math.cos(rad)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _canonical_centers() -> np.ndarray:
    axes = [
        CANONICAL_ORIGIN[axis] + CANONICAL_SPACING * np.arange(CANONICAL_SHAPE[axis])
        for axis in range(3)
    ]
    gx, gy, gz = np.meshgrid(*axes, indexing="ij")
    return np.stack(
        [gx.ravel(order="F"), gy.ravel(order="F"), gz.ravel(order="F")], axis=1
    )


def _body_frame(mesh_extent: np.ndarray) -> np.ndarray:
    return mesh_extent / 2.0


def build_shape(
    definition: ShapeDefinition,
    *,
    active_mask: np.ndarray | None = None,
) -> AnalyticShape:
    """Binary occupancy at canonical cell centers plus the analytic anchor mesh.

    ``active_mask`` (optional flat bool in canonical x-fastest order) is ANDed
    into the occupancy so cell centers outside the fixture's active design
    cells are excluded; whether it was applied is recorded by the exporter.
    """

    d = definition
    copies = d.parts if d.parts else (d,)
    occupancy = np.zeros(math.prod(CANONICAL_SHAPE), dtype=bool)
    for part in copies:
        rotation = _rotation_about_y(part.angle_y_deg)
        center = np.asarray(part.center_m, dtype=float)
        half = np.array([part.chord_m, part.span_m, part.thickness_m]) / 2.0
        body = (_canonical_centers() - center) @ rotation
        inside = np.all(np.abs(body) <= half[None, :] + 1e-12, axis=1)
        occupancy = occupancy | inside

    occupancy = occupancy.astype(bool)
    if active_mask is not None:
        if active_mask.shape != (math.prod(CANONICAL_SHAPE),):
            raise ValueError(
                "active_mask must be a flat bool array of the canonical cell count"
            )
        occupancy = occupancy & np.asarray(active_mask, dtype=bool)

    mesh_bytes = _anchor_stl_bytes(d)
    return AnalyticShape(
        definition=d,
        occupancy=occupancy,
        stl_bytes_sha256=hashlib.sha256(mesh_bytes).hexdigest(),
        occupancy_npy_sha256=_npy_bytes_sha256(occupancy),
    )


def _part_boxes(d: ShapeDefinition) -> list[ShapeDefinition]:
    return list(d.parts) if d.parts else [d]


def _anchor_stl_bytes(d: ShapeDefinition) -> bytes:
    mesh = anchor_mesh(d)
    return trimesh.exchange.stl.export_stl(mesh)


def anchor_mesh(d: ShapeDefinition) -> trimesh.Trimesh:
    mesh: trimesh.Trimesh | None = None
    for part in _part_boxes(d):
        single = trimesh.creation.box(extents=[part.chord_m, part.span_m, part.thickness_m])
        transform = np.eye(4)
        transform[:3, :3] = _rotation_about_y(part.angle_y_deg)
        transform[:3, 3] = np.asarray(part.center_m, dtype=float)
        single.apply_transform(transform)
        if not single.is_watertight:
            raise ValueError(f"analytic anchor mesh part of {d.shape_id!r} is not watertight")
        mesh = single if mesh is None else (mesh + single)
    assert mesh is not None
    if not mesh.is_watertight:
        raise ValueError(f"analytic anchor mesh for {d.shape_id!r} is not watertight")
    return mesh


def _npy_bytes_sha256(values: np.ndarray) -> str:
    buffer = io.BytesIO()
    np.save(buffer, np.ascontiguousarray(values, dtype=np.bool_), allow_pickle=False)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


def export_shape(
    shape: AnalyticShape,
    output_dir: str | Path,
    *,
    active_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """Write occupancy npy + anchor STL + per-shape manifest, and return stats.

    The manifest binds ``shape_id``, the definition, both SHA-256 hashes, the
    shared geometry identity, and an occupancy/anchor re-voxelized IoU check so
    both representations can be confirmed to describe the same object.
    """

    d = shape.definition
    out = Path(output_dir).resolve() / d.shape_id
    out.mkdir(parents=True, exist_ok=True)

    stl_path = out / "anchor.stl"
    stl_path.write_bytes(_anchor_stl_bytes(d))
    if hashlib.sha256(stl_path.read_bytes()).hexdigest() != shape.stl_bytes_sha256:
        raise ValueError("re-exported anchor STL does not reproduce the bound SHA-256")

    npy_path = out / "occupancy.npy"
    np.save(npy_path, np.ascontiguousarray(shape.occupancy, dtype=np.bool_), allow_pickle=False)
    if _npy_bytes_sha256(shape.occupancy) != hashlib.sha256(npy_path.read_bytes()).hexdigest():
        raise ValueError("re-exported occupancy npy does not reproduce the bound hash")

    mesh = anchor_mesh(d)
    spacing = CANONICAL_SPACING
    occ_volume = float(shape.occupancy.sum() * spacing**3)
    rasterized = _voxelize_stl(mesh).ravel(order="F")
    union = int((rasterized | shape.occupancy).sum())
    iou = int((rasterized & shape.occupancy).sum()) / union if union else 1.0
    manifest = {
        "schema_version": _SCHEMA_VERSION,
        "kind": "analytic_candidate_shape",
        "geometry_id": d.shape_id,
        "definition": asdict(d),
        "canonical_grid": {
            "shape_cells": list(CANONICAL_SHAPE),
            "spacing_m": CANONICAL_SPACING,
            "origin_m": list(CANONICAL_ORIGIN),
            "cell_order": "x-fastest (flat = arr3.ravel(order='F') of [i, j, k])",
        },
        "active_mask_intersected": active_mask is not None,
        "files": {
            "occupancy_npy": {"path": "occupancy.npy", "sha256": hashlib.sha256(npy_path.read_bytes()).hexdigest()},
            "anchor_stl": {"path": "anchor.stl", "sha256": shape.stl_bytes_sha256},
        },
        "occupancy_volume_m3": occ_volume,
        "anchor_stl_volume_m3": float(abs(mesh.volume)),
        "anchor_bounds_m": np.asarray(mesh.bounds).tolist(),
        "revoxelization_iou": iou,
        "anchor_stl_watertight": bool(mesh.is_watertight),
    }
    if active_mask is not None:
        manifest["active_mask_cells"] = int(np.count_nonzero(np.asarray(active_mask, dtype=bool)))
    (out / "shape_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _voxelize_stl(mesh: trimesh.Trimesh, cell_shape=(60, 32, 24)) -> np.ndarray:
    """Boolean occupancy of canonical cell centers inside the analytic mesh."""

    from trimesh.proximity import signed_distance

    shape = tuple(int(v) for v in cell_shape)
    sd = signed_distance(mesh, _canonical_centers())
    # trimesh signed_distance is positive inside the watertight mesh; faces
    # aligned with cell centers give sd ~ +-1e-16, so keep an inclusive band
    return (sd > -1.0e-9).reshape(shape, order="F")


def rotated_corner_extents(d: ShapeDefinition) -> tuple[float, float, float]:
    """Axis-aligned extent of the rotated anchor box (for envelope checks)."""

    half = np.array([d.chord_m, d.span_m, d.thickness_m]) / 2.0
    corners = np.array(
        [
            [sx * half[0], sy * half[1], sz * half[2]]
            for sx in (-1.0, 1.0)
            for sy in (-1.0, 1.0)
            for sz in (-1.0, 1.0)
        ]
    ) @ _rotation_about_y(d.angle_y_deg).T
    return tuple(float(v) for v in (corners.max(axis=0) - corners.min(axis=0)))


__all__ = [
    "AnalyticShape",
    "ShapeDefinition",
    "anchor_mesh",
    "build_shape",
    "export_shape",
    "rotated_corner_extents",
    "shape_definitions",
]
