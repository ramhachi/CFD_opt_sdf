import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np
import pytest

from xfid45_surface_round2_candidates import (
    H_M,
    extract_candidate,
    face_components,
    orient_components,
    sample_phi,
    sample_phi_gradient,
)


def sphere_field(n=25, h=H_M, radius=0.24):
    axis = (np.arange(n) - (n - 1) / 2) * h
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.sqrt(x * x + y * y + z * z) - radius, np.array([axis[0]] * 3)


def shell_field(n=29, h=H_M, inner=0.20, outer=0.30):
    axis = (np.arange(n) - (n - 1) / 2) * h
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    radius = np.sqrt(x * x + y * y + z * z)
    return np.maximum(inner - radius, radius - outer), np.array([axis[0]] * 3)


def undirected_faces(faces):
    return np.sort(np.asarray(faces), axis=1)


def test_vectorized_trilinear_value_and_gradient_on_affine_field():
    h = 0.2
    origin = np.array([-1.0, 2.0, -0.5])
    axes = [origin[i] + h * np.arange(4) for i in range(3)]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    phi = 2.0 * x - 3.0 * y + 0.5 * z + 4.0
    points = np.array([[-0.91, 2.23, -0.32], [-0.65, 2.49, 0.01]])
    expected = 2 * points[:, 0] - 3 * points[:, 1] + 0.5 * points[:, 2] + 4
    np.testing.assert_allclose(sample_phi(phi, origin, h, points), expected, atol=1e-14)
    np.testing.assert_allclose(
        sample_phi_gradient(phi, origin, h, points), [[2, -3, 0.5]] * 2, atol=1e-14
    )


@pytest.mark.parametrize("name", ["A", "B", "C"])
def test_sphere_has_one_outward_oriented_component_without_geometry_changes(name):
    if name == "B":
        module = pytest.importorskip("skimage")
        if module.__version__ != "0.25.2":
            pytest.skip("round2 pins scikit-image 0.25.2")
    phi, origin = sphere_field()
    before = phi.copy()
    vertices, faces, audit = extract_candidate(name, phi, origin, H_M)
    assert len(vertices) > 0 and len(faces) > 0
    assert len(face_components(faces)) == 1
    component = audit["orientation"]["components"][0]
    assert component["orientation_contract_pass"]
    assert component["stable_sidedness"] in {"outward", "inward"}
    assert component["delta_votes"] == [component["stable_sidedness"]] * 3
    assert component["oriented_signed_volume_m3"] > 0
    assert audit["canonical_phi_mutated"] is False
    assert audit["source_field_unchanged"] is True
    np.testing.assert_array_equal(phi, before)


def test_cavity_component_is_allowed_to_have_negative_oriented_volume():
    phi, origin = shell_field()
    vertices, faces, audit = extract_candidate("C", phi, origin, H_M)
    components = audit["orientation"]["components"]
    assert len(components) == 2
    assert all(row["orientation_contract_pass"] for row in components)
    assert sorted(row["volume_class"] for row in components) == [
        "solid_boundary",
        "void_boundary",
    ]
    assert any(row["oriented_signed_volume_m3"] < 0 for row in components)
    assert len(vertices) > 0 and len(faces) > 0


@pytest.mark.parametrize("name", ["B", "C"])
def test_exact_zero_tie_is_positive_and_repeatable(name):
    if name == "B":
        module = pytest.importorskip("skimage")
        if module.__version__ != "0.25.2":
            pytest.skip("round2 pins scikit-image 0.25.2")
    h = H_M
    axis = (np.arange(21) - 10) * h
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    phi = x.copy()  # x=0 grid plane is an exact-zero symbolic tie surface.
    original = phi.copy()
    origin = np.array([axis[0]] * 3)
    v1, f1, a1 = extract_candidate(name, phi, origin, h)
    v2, f2, a2 = extract_candidate(name, phi, origin, h)
    np.testing.assert_array_equal(v1, v2)
    np.testing.assert_array_equal(f1, f2)
    np.testing.assert_array_equal(phi, original)
    assert a1["extractor"]["zero_tie_sign"] == "positive-fluid"
    assert a1["extractor"]["exact_zero_node_count"] == np.count_nonzero(phi == 0)
    if name == "C":
        keys = [
            tuple(row)
            for row in a1["extractor"]["vertex_source_edge_keys_global_c_order"]
        ]
        assert len(keys) == len(set(keys)) == len(v1)
        assert all(key[0] < key[1] for key in keys)


def test_component_flip_only_reverses_winding_not_vertices_or_connectivity():
    phi, origin = sphere_field()
    vertices, faces, _ = extract_candidate("C", phi, origin, H_M)
    reversed_faces = faces[:, [0, 2, 1]]
    reoriented, audit = orient_components(vertices, reversed_faces, phi, origin, H_M)
    np.testing.assert_array_equal(vertices, vertices.copy())
    np.testing.assert_array_equal(undirected_faces(reoriented), undirected_faces(faces))
    assert np.array_equal(reoriented[:, 0], reversed_faces[:, 0])
    assert audit["components"][0]["whole_component_flipped"] is True
    assert audit["components"][0]["oriented_signed_volume_m3"] > 0
