from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "work/xfid45_surface_round2_deps"))

from xfid45_round3_export import _refine, extract, orient, topology  # noqa: E402
from verify_xfid45_round3 import (  # noqa: E402
    fidelity as verify_fidelity,
    orientation as verify_orientation,
)


def _cube(center, radius):
    c = np.asarray(center, dtype=float)
    v = c + radius * np.array(
        [
            [-1, -1, -1],
            [1, -1, -1],
            [1, 1, -1],
            [-1, 1, -1],
            [-1, -1, 1],
            [1, -1, 1],
            [1, 1, 1],
            [-1, 1, 1],
        ],
        dtype=float,
    )
    # Consistently outward, two triangles per cube side.
    f = np.array(
        [
            [0, 2, 1],
            [0, 3, 2],
            [4, 5, 6],
            [4, 6, 7],
            [0, 1, 5],
            [0, 5, 4],
            [1, 2, 6],
            [1, 6, 5],
            [2, 3, 7],
            [2, 7, 6],
            [3, 0, 4],
            [3, 4, 7],
        ],
        dtype=np.int64,
    )
    return v, f


def _tetra(offset=(0.0, 0.0, 0.0)):
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float) + offset
    f = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int64)
    return v, f


def _signed_box(p, radius):
    q = np.abs(p) - radius
    return np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(np.max(q, axis=-1), 0)


def test_extract_refines_affine_field_and_preserves_source():
    pytest.importorskip("skimage")
    x, y, z = np.meshgrid(np.arange(5), np.arange(4), np.arange(6), indexing="ij")
    phi = (0.2 * x - 0.3 * y + 0.1 * z - 0.7).astype(np.float64)
    saved = phi.copy()
    vertices, faces, audit = extract(phi, (-1.0, 2.0, 0.5), 0.025, 4)
    assert vertices.shape[1] == 3 and faces.shape[1] == 3
    assert audit["refined_shape"] == [17, 13, 21]
    assert audit["source_phi_unmodified"] is True
    assert np.array_equal(phi, saved)
    # Coordinates are in physical grid units, so the affine zero plane is exact.
    affine = (
        0.2 * (vertices[:, 0] + 1) / 0.025
        - 0.3 * (vertices[:, 1] - 2) / 0.025
        + 0.1 * (vertices[:, 2] - 0.5) / 0.025
        - 0.7
    )
    assert np.max(np.abs(affine)) < 5e-8


def test_refinement_reproduces_trilinear_bilinear_field_and_endpoints():
    i, j, k = np.meshgrid(np.arange(4), np.arange(5), np.arange(3), indexing="ij")
    field = (0.13 * i * j - 0.2 * j + 0.4 * k + 0.07 * i).astype(np.float64)
    r = 4
    refined = _refine(field, r)
    fi, fj, fk = np.meshgrid(
        np.arange(13) / r, np.arange(17) / r, np.arange(9) / r, indexing="ij"
    )
    expected = 0.13 * fi * fj - 0.2 * fj + 0.4 * fk + 0.07 * fi
    assert refined.shape == expected.shape == (13, 17, 9)
    assert np.allclose(refined, expected, rtol=0, atol=2e-14)
    assert np.array_equal(refined[::r, ::r, ::r], field)


def test_exact_zero_tie_uses_original_spacing_for_every_refinement():
    pytest.importorskip("skimage")
    phi = np.broadcast_to(
        np.arange(-2, 3, dtype=np.float64)[:, None, None] - 2.0, (5, 5, 5)
    ).copy()
    phi[2, 2, 2] = 0.0
    near_zero = np.nextafter(0.0, 1.0)
    phi[2, 1, 2] = near_zero
    original = phi.copy()
    _, _, audit1 = extract(phi, (-0.05, -0.05, -0.05), 0.025, 1)
    _, _, audit4 = extract(phi, (-0.05, -0.05, -0.05), 0.025, 4)
    assert (
        audit1["scratch_exact_zeros_set_to_positive_tau_m"]
        == audit4["scratch_exact_zeros_set_to_positive_tau_m"]
    )
    assert audit1["scratch_exact_zeros_set_to_positive_tau_m"] == float(
        np.float32(0.025 * 2.0**-20)
    )
    assert audit1["exact_zero_count_before_tie"] == audit1["scratch_values_changed"]
    assert audit4["exact_zero_count_before_tie"] == audit4["scratch_values_changed"]
    assert audit1["nonzero_to_float32_zero_count"] > 0
    assert audit1["float32_cast_lineage_pass"] is False
    assert np.array_equal(phi, original)


def test_hollow_shell_orients_outer_and_void_components_by_field():
    outer_v, outer_f = _cube((0, 0, 0), 0.5)
    inner_v, inner_f = _cube((0, 0, 0), 0.25)
    vertices = np.vstack((outer_v, inner_v))
    faces = np.vstack((outer_f, inner_f + len(outer_v)))
    axis = np.arange(-32, 33, dtype=float) * 0.025
    xx, yy, zz = np.meshgrid(axis, axis, axis, indexing="ij")
    p = np.stack((xx, yy, zz), axis=-1)
    phi = np.maximum(_signed_box(p, 0.5), -_signed_box(p, 0.25))
    oriented, audit = orient(vertices, faces, phi, (-0.8, -0.8, -0.8), 0.025)
    assert audit["topology"]["topology_pass"]
    assert audit["status"] == "PASS"
    assert [row["volume_class"] for row in audit["components"]] == [
        "solid_boundary",
        "void_boundary",
    ]
    assert audit["components"][0]["whole_component_flipped"] is False
    assert audit["components"][1]["whole_component_flipped"] is True
    assert topology(vertices, oriented)["winding_consistent"]


@pytest.mark.parametrize("kind", ["degenerate", "three_face_edge", "pinched_vertex"])
def test_invalid_topology_is_n_a_and_never_flips(kind):
    if kind == "degenerate":
        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        faces = np.array([[0, 1, 2], [0, 0, 1]], dtype=np.int64)
    elif kind == "three_face_edge":
        vertices = np.array(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1]], dtype=float
        )
        faces = np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]], dtype=np.int64)
    else:
        a_v, a_f = _tetra()
        b_v, b_f = _tetra((3, 0, 0))
        b_v[0] = a_v[0]
        vertices = np.vstack((a_v, b_v[1:]))
        faces = np.vstack((a_f, np.where(b_f == 0, 0, b_f + 3)))
    stats = topology(vertices, faces)
    phi = np.ones((8, 8, 8), dtype=float)
    oriented, audit = orient(vertices, faces, phi, (-1, -1, -1), 0.5)
    assert stats["topology_pass"] is False
    assert audit["status"] == "N/A"
    assert audit["reason"] == "topology prerequisite failed"
    assert np.array_equal(oriented, faces)
    if kind == "three_face_edge":
        assert stats["nonmanifold_edge_count"] >= 1
        assert stats["edge_connected_component_count"] == 1
    if kind == "pinched_vertex":
        assert stats["vertex_link_bad_count"] >= 1
        assert stats["edge_connected_component_count"] == 2


def test_component_ids_use_minimum_original_face_id_and_float32_collision_is_detectable():
    a_v, a_f = _tetra()
    b_v, b_f = _tetra((2, 0, 0))
    vertices = np.vstack((a_v, b_v))
    faces = np.vstack(
        (b_f + 4, a_f)
    )  # component zero occurs after component one in face order
    stats = topology(vertices, faces)
    assert stats["component_min_original_face_id"] == [0, 4]
    close = np.array([[1, 0, 0], [1 + 1e-8, 0, 0], [0, 1, 0]], dtype=np.float64)
    assert len(np.unique(close, axis=0)) == 3
    assert len(np.unique(close.astype(np.float32), axis=0)) == 2


def test_clearance_is_reported_separately_from_topology_pass():
    vertices, faces = _tetra((3.0, 0.0, 0.0))
    stats = topology(vertices, faces)
    assert stats["topology_pass"] is True
    assert stats["stage_v_clearance_pass"] is False


def test_fidelity_numeric_status_is_separate_from_geometry_qualification():
    vertices, faces = _cube((0, 0, 0), 0.5)
    axis = np.arange(-32, 33, dtype=float) * 0.025
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    p = np.stack((x, y, z), axis=-1)
    phi = _signed_box(p, 0.5)
    duplicate_face_surface = np.vstack((faces, faces[:1]))
    scored = verify_fidelity(
        vertices,
        faces,
        vertices,
        duplicate_face_surface,
        phi,
        phi,
        (-0.8, -0.8, -0.8),
        0.025,
    )
    orientation_audit = verify_orientation(
        vertices, duplicate_face_surface, phi, (-0.8, -0.8, -0.8), 0.025
    )
    assert scored["within_limit"] is True
    assert scored["geometry_prerequisite_pass"] is False
    assert orientation_audit["status"] == "N/A"
