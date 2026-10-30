import numpy as np
import trimesh

from cfd_sdf.surface_canonicalization import (
    canonicalize_triangle_surface,
    trilinear_gradient,
)


def test_trilinear_gradient_recovers_linear_field_gradient():
    origin = np.array((-1.0, -1.0, -1.0))
    spacing = 0.5
    axes = [origin[i] + spacing * np.arange(5) for i in range(3)]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    phi = x + 2.0 * y - 3.0 * z

    gradient, cell, corners = trilinear_gradient(
        phi, origin, spacing, np.array((-0.75, -0.4, 0.2))
    )

    np.testing.assert_allclose(gradient, (1.0, 2.0, -3.0), atol=1e-14)
    assert cell == (0, 1, 2)
    assert corners.shape == (2, 2, 2)


def test_canonicalization_preserves_coordinates_and_orients_sphere_by_phi():
    source = trimesh.creation.icosphere(subdivisions=2, radius=0.35)
    faces = source.faces[:, ::-1].copy()
    duplicated_source_vertex = int(faces[0, 0])
    vertices = np.vstack(
        (
            source.vertices,
            source.vertices[duplicated_source_vertex],
            ((0.21, 0.0, 0.0), (0.24, 0.0, 0.0), (0.27, 0.0, 0.0)),
        )
    )
    faces[0, 0] = len(source.vertices)
    faces = np.vstack(
        (
            faces,
            faces[0, (0, 2, 1)],
            (0, 0, 1),
            (len(vertices) - 3, len(vertices) - 2, len(vertices) - 1),
        )
    )

    origin = (-1.0, -1.0, -1.0)
    spacing = 0.05
    axis = np.asarray(origin[0]) + spacing * np.arange(41)
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    phi = np.sqrt(x * x + y * y + z * z) - 0.35
    raw_unique_coordinates = np.unique(vertices, axis=0)

    result = canonicalize_triangle_surface(
        vertices,
        faces,
        phi=phi,
        origin_m=origin,
        spacing_m=spacing,
    )

    np.testing.assert_array_equal(result.vertices, raw_unique_coordinates)
    assert result.audit["exact_coincident_vertex_instances_merged"] == 1
    assert result.audit["duplicate_triangle_count_removed"] == 1
    assert result.audit["repeated_index_triangle_count_removed"] == 1
    assert result.audit["exact_zero_area_triangle_count_removed"] == 1
    assert result.audit["ambiguous_face_ids_after_cleanup"] == []
    assert result.audit["flipped_face_ids_after_cleanup"]

    oriented = trimesh.Trimesh(
        vertices=result.vertices, faces=result.faces, process=False
    )
    assert oriented.is_watertight
    assert oriented.is_winding_consistent
    assert oriented.volume > 0.0
    for face in result.faces:
        centroid = result.vertices[face].mean(axis=0)
        gradient, _, _ = trilinear_gradient(phi, origin, spacing, centroid)
        normal = np.cross(
            result.vertices[face[1]] - result.vertices[face[0]],
            result.vertices[face[2]] - result.vertices[face[0]],
        )
        assert np.dot(normal, gradient) > 0.0


def test_canonicalization_rejects_non_integer_face_indices():
    with np.testing.assert_raises_regex(ValueError, "integer vertex indices"):
        canonicalize_triangle_surface(
            np.eye(3),
            np.array(((0.0, 1.0, 2.0),)),
            phi=np.zeros((2, 2, 2)),
            origin_m=(0.0, 0.0, 0.0),
            spacing_m=1.0,
        )
