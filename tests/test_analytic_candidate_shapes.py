from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from cfd_sdf.analytic_candidate_shapes import (
    AnalyticShape,
    ShapeDefinition,
    build_shape,
    export_shape,
    rotated_corner_extents,
    shape_definitions,
)

USABLE_CENTER_BOX = ((-0.7, 1.65), (-0.5, 0.45), (-0.3, 0.25))


def test_ten_shapes_are_preregistered() -> None:
    ids = list(shape_definitions())
    assert len(ids) == 10
    assert "plate_a00_ref" in ids and "plate_a30_nd" in ids and "box_bluff03" in ids
    assert len(set(ids)) == len(ids)


def test_occupancy_and_anchor_share_one_geometry(tmp_path: Path) -> None:
    center = (0.4, 0.05, 0.0)
    d = ShapeDefinition("check_plate", 0.6, 0.8, 0.15, 20.0, center)
    shape = build_shape(d)

    manifest = export_shape(shape, tmp_path)

    stl = trimesh.load_mesh(tmp_path / "check_plate" / "anchor.stl")
    assert stl.is_watertight
    assert manifest["anchor_stl_volume_m3"] == pytest.approx(0.6 * 0.8 * 0.15, rel=1e-9)
    assert manifest["revoxelization_iou"] >= 0.8
    assert manifest["files"]["anchor_stl"]["sha256"] == hashlib.sha256(
        (tmp_path / "check_plate" / "anchor.stl").read_bytes()
    ).hexdigest()
    assert manifest["files"]["occupancy_npy"]["sha256"] == hashlib.sha256(
        (tmp_path / "check_plate" / "occupancy.npy").read_bytes()
    ).hexdigest()


def test_occupancy_is_exact_for_axis_aligned_box(tmp_path: Path) -> None:
    d = ShapeDefinition("check_box", 0.3, 0.3, 0.3, 0.0, (0.4, 0.05, 0.0))
    shape = build_shape(d)
    # cell centers at exact half-grid offsets: 7 cells per axis (inclusive faces)
    assert int(shape.occupancy.sum()) == 343
    manifest = export_shape(shape, tmp_path)
    assert manifest["anchor_stl_volume_m3"] == pytest.approx(0.3**3, rel=1e-9)
    assert manifest["revoxelization_iou"] == pytest.approx(1.0)


def test_rotation_convention_nose_down_displaces_nose_to_minus_z() -> None:
    from cfd_sdf.analytic_candidate_shapes import anchor_mesh

    d = ShapeDefinition("check_rot", 0.6, 0.4, 0.1, 20.0, (0.0, 0.0, 0.0))
    mesh = anchor_mesh(d)
    c, s = float(np.cos(np.deg2rad(20.0))), float(np.sin(np.deg2rad(20.0)))
    # rotated box: z extent = 2 * (|s| * chord/2 + |c| * thickness/2);
    # for +20 deg (nose down) the +x nose maps to z = -s * chord/2, so zmin
    # is NOT symmetric: zmin_reaches -s*chord by the mid-plane... bounds check:
    # corner set is symmetric under theta sign flip only in x; verify explicitly.
    extent = rotated_corner_extents(d)
    expected_z = 2.0 * (s * d.chord_m / 2.0 + c * d.thickness_m / 2.0)
    assert extent[2] == pytest.approx(expected_z, rel=1e-9)
    # the body-frame nose (+x) maps to negative world z for positive angle
    rotation = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    nose_world = rotation @ np.array([d.chord_m / 2.0, 0.0, 0.0])
    assert nose_world[2] < 0.0
    up_rotation = np.array([[c, 0.0, -s], [0.0, 1.0, 0.0], [s, 0.0, c]])
    nose_world_up = up_rotation @ np.array([d.chord_m / 2.0, 0.0, 0.0])
    assert nose_world_up[2] > 0.0


def test_shapes_fit_inside_usable_box_and_clearance(tmp_path: Path) -> None:
    """Every pre-registered shape must fit the usable center box, so the anchor
    STL keeps >= 0.25 m clearance to the declared Stage V far-field (the
    stage_v_clearance_v1 margin), keeping the ranking set meshable."""

    from cfd_sdf.analytic_candidate_shapes import CANONICAL_ORIGIN, CANONICAL_SPACING

    fixed_lower = (-1.0, -0.8, -0.6)
    fixed_upper = (2.0, 0.8, 0.6)
    for shape_id, d in shape_definitions().items():
        shape = build_shape(d)
        idx = np.flatnonzero(shape.occupancy)
        assert idx.size > 0, shape_id
        nx, ny, nz = (60, 32, 24)
        ix, iy, iz = idx % nx, (idx // nx) % ny, idx // (nx * ny)
        center_lo = np.array([
            CANONICAL_ORIGIN[0] + ix.min() * CANONICAL_SPACING,
            CANONICAL_ORIGIN[1] + iy.min() * CANONICAL_SPACING,
            CANONICAL_ORIGIN[2] + iz.min() * CANONICAL_SPACING,
        ])
        center_hi = np.array([
            CANONICAL_ORIGIN[0] + ix.max() * CANONICAL_SPACING,
            CANONICAL_ORIGIN[1] + iy.max() * CANONICAL_SPACING,
            CANONICAL_ORIGIN[2] + iz.max() * CANONICAL_SPACING,
        ])
        face_lo = center_lo - CANONICAL_SPACING / 2.0
        face_hi = center_hi + CANONICAL_SPACING / 2.0
        clearances = np.concatenate([face_lo - np.asarray(fixed_lower), np.asarray(fixed_upper) - face_hi])
        assert clearances.min() >= 0.25 - 1e-9, (shape_id, clearances.min())
        for axis, (lo, hi) in enumerate(USABLE_CENTER_BOX):
            assert lo <= center_lo[axis] and center_hi[axis] <= hi, (shape_id, axis)


def test_build_shape_respects_active_mask(tmp_path: Path) -> None:
    d = shape_definitions()["plate_a00_ref"]
    fake_active = np.zeros(60 * 32 * 24, dtype=bool)
    shape = build_shape(d, active_mask=fake_active)
    assert int(shape.occupancy.sum()) == 0

    half_active = np.zeros(60 * 32 * 24, dtype=bool)
    mid = 30
    for i in range(60):
        for j in range(32):
            for k in range(24):
                if i < mid:
                    half_active[i + j * 60 + k * 60 * 32] = True
    shape = build_shape(d, active_mask=half_active)
    assert int(shape.occupancy.sum()) < 2000


def test_export_rejects_tampered_shapes(tmp_path: Path) -> None:
    d = shape_definitions()["plate_a00_ref"]
    shape = build_shape(d)
    tampered = AnalyticShape(
        definition=d,
        occupancy=shape.occupancy,
        stl_bytes_sha256="0" * 64,
        occupancy_npy_sha256=shape.occupancy_npy_sha256,
    )
    with pytest.raises(ValueError, match="reproduce the bound SHA-256"):
        export_shape(tampered, tmp_path)
