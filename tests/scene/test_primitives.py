"""Solver-free primitive checks; deformed plates use an independent zero set."""
import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest
import trimesh
from scipy.spatial import cKDTree

from cfd_gen.scene.primitives import BoxBody, EndplatePlate, MeshBody, PlateElement


def gradient(body, points, epsilon=1e-6):
    return np.stack(
        [(body.phi(points + epsilon * e) - body.phi(points - epsilon * e)) / (2 * epsilon)
         for e in np.eye(points.shape[-1])], axis=-1,
    )


def raw_section(points, chord, thickness, camber=0.0, reflex=0.0):
    u, v = np.moveaxis(points, -1, 0)
    s = np.clip(2 * u / chord, -1, 1)
    w = v + camber * (s * s - 1 / 3) + reflex * (s ** 3 - 0.6 * s)
    return np.hypot(np.maximum(np.abs(u) - chord / 2, 0), w) - thickness / 2


def dense_zero_set(chord, thickness, camber, reflex, count=50001):
    """Independent v18 parameterisation, including the two half-circle caps."""
    u = np.linspace(-chord / 2, chord / 2, count)
    s = 2 * u / chord
    f = camber * (s ** 2 - 1 / 3) + reflex * (s ** 3 - 0.6 * s)
    sides = [np.column_stack((u, -f + sign * thickness / 2)) for sign in (-1, 1)]
    theta = np.linspace(-np.pi / 2, np.pi / 2, count // 8)
    for sign in (-1, 1):
        fc = camber * (1 - 1 / 3) + reflex * (sign - 0.6 * sign)
        sides.append(np.column_stack((sign * chord / 2 + sign * thickness / 2 * np.cos(theta),
                                      -fc + thickness / 2 * np.sin(theta))))
    return np.concatenate(sides)


def test_flat_stadium_distance_and_rotation():
    p = PlateElement("wing", 0.3, -0.2, 1.0, 0.1, angle=0.31, span=0.8, y=0.4)
    local = np.array([[0.1, 0.16], [-0.6, -0.12], [0.51, 0.07], [0.2, -0.02]])
    ca, sa = np.cos(p.angle), np.sin(p.angle)
    points = local @ np.array([[ca, sa], [-sa, ca]]) + [p.x, p.z]
    np.testing.assert_allclose(p.phi(points), raw_section(local, p.chord, p.thickness), atol=1e-16)
    np.testing.assert_allclose(np.linalg.norm(gradient(p, points), axis=-1), 1, atol=1e-8)
    xyz = np.column_stack((points[:, 0], np.full(len(points), p.y), points[:, 1]))
    np.testing.assert_array_equal(p.phi(xyz), p.phi(points))
    # Exact Cartesian extrusion: outside both section and flat end is a Euclidean corner.
    tip = np.array([[p.x, p.y + 0.5, p.z + 0.2]])
    section = p.phi(tip[:, [0, 2]])[0]
    assert p.phi(tip)[0] == pytest.approx(np.hypot(max(section, 0), 0.1))
    xyz = np.array([[p.x, p.y + 0.5, p.z], [p.x + 0.7, p.y + 0.6, p.z + 0.2],
                    [p.x + 0.1, p.y + 0.1, p.z + 0.2]])
    np.testing.assert_allclose(np.linalg.norm(gradient(p, xyz), axis=-1), 1, atol=1e-8)


@pytest.mark.parametrize("camber,reflex", [(0.0, 0.0), (0.06, 0), (0, 0.04),
                                               (0.06, 0.04), (0.06, -0.04),
                                               (-0.06, 0.04), (-0.06, -0.04)])
@pytest.mark.parametrize("dimension", [2,3])
def test_deformed_band_against_dense_zero_set(camber, reflex, dimension):
    thickness, h = 0.1, 0.025
    p = PlateElement("wing", 0, 0, 1, thickness, camber=camber, reflex=reflex)
    rng = np.random.default_rng(610)
    points = rng.uniform([-0.57, -0.17], [0.57, 0.17], (1700, 2)) if dimension==2 else rng.uniform(
        [-.57,-.7,-.17],[.57,.7,.17],(1700,3))
    phi = p.phi(points)
    points, phi = points[np.abs(phi) <= 2 * h], phi[np.abs(phi) <= 2 * h]
    section_points = points if dimension==2 else points[:,[0,2]]
    raw = raw_section(section_points, 1, thickness, camber, reflex)
    if dimension==3:
        dy = np.abs(points[:,1])-p.span/2
        raw = np.minimum(np.maximum(raw,dy),0)+np.hypot(np.maximum(raw,0),np.maximum(dy,0))
    np.testing.assert_array_equal(phi < 0, raw < 0)
    reference = cKDTree(dense_zero_set(1, thickness, camber, reflex)).query(section_points)[0]
    section_raw = raw_section(section_points,1,thickness,camber,reflex)
    signed_reference = np.where(section_raw < 0, -reference, reference)
    if dimension==3:
        signed_reference = np.minimum(np.maximum(signed_reference,dy),0)+np.hypot(np.maximum(signed_reference,0),np.maximum(dy,0))
    assert np.max(np.abs(phi - signed_reference)) <= 0.02 * thickness
    assert np.median(np.abs(np.linalg.norm(gradient(p, points), axis=-1) - 1)) <= 0.10


def test_deformed_zero_surface_is_v18_surface():
    p = PlateElement("wing", 0, 0, 1, 0.08, camber=0.06, reflex=-0.04)
    surface = dense_zero_set(1, 0.08, 0.06, -0.04, count=301)
    assert np.max(np.abs(p.phi(surface))) < 1e-14
    assert np.max(np.abs(raw_section(surface, 1, 0.08, 0.06, -0.04))) < 1e-14


def test_endplate_exact_box_sdf():
    p = EndplatePlate("end", 1, 2, 3, 0.8, 1, 0.1)
    points = np.array([[1, 2, 3], [1.6, 2.15, 3.5], [1, 2.03, 3.42]])
    np.testing.assert_allclose(p.phi(points), [-0.05, np.sqrt(0.03), 0.02], atol=1e-15)
    np.testing.assert_allclose(np.linalg.norm(gradient(p, points[1:]), axis=-1), 1, atol=1e-8)
    np.testing.assert_allclose(p.phi([[1, 3], [1.6, 3.5]]), [-0.4, np.sqrt(0.02)])


def test_box_sphere_exact_and_generic_field_semantics():
    sphere = BoxBody("sphere", (1, 2, 3), (0.5, 0.5, 0.5))
    points = np.array([[1.1, 2.2, 3.3], [0.2, 2.1, 2.9]])
    np.testing.assert_allclose(sphere.phi(points), np.linalg.norm(points - [1, 2, 3], axis=-1) - 0.5)
    np.testing.assert_allclose(np.linalg.norm(gradient(sphere, points), axis=-1), 1, atol=1e-8)
    box = BoxBody("rounded", (0, 0, 0), (1, 0.8, 0.6), exponent=4)
    surface = box.boundary_points(0.04)
    assert np.max(np.abs(box.phi(surface))) < 1e-14
    # The normalized implicit approximation has first-order distance behaviour at its zero set.
    near = surface[::17] * 1.01
    assert np.median(np.abs(np.linalg.norm(gradient(box, near), axis=-1) - 1)) < 0.05
    assert box.phi(np.zeros((1, 3)))[0] == pytest.approx(-0.6)
    # Anisotropic gradient normalization has a direction-dependent centre limit
    # unless its deep-interior continuation is made explicit and continuous.
    for dimension in (2, 3):
        approaches = np.vstack((np.zeros(dimension), 1e-9 * np.eye(dimension), -1e-9 * np.eye(dimension)))
        np.testing.assert_allclose(box.phi(approaches), -0.6, atol=2e-9, rtol=0)


def test_anisotropic_box_continuation_is_continuous_but_not_ray_monotone():
    box = BoxBody("ellipsoid", (0, 0, 0), (2, .8, .4))
    # The deep-interior continuation is not an exact distance: depth can first
    # increase along an outward ray, although the centre limit is continuous.
    np.testing.assert_allclose(box.phi([[0, 0, 0], [1, 0, 0], [2, 0, 0]]), [-.4, -1., 0.])
    np.testing.assert_allclose(box.phi(1e-10 * np.eye(3)), -.4, atol=2e-10, rtol=0)


def test_primitive_numeric_inputs_normalize_negative_zero():
    bodies = [PlateElement("p", -0., -0., 1, .1, angle=-0., camber=-0., reflex=-0., y=-0.),
              EndplatePlate("e", -0., -0., -0., 1, 1, .1),
              BoxBody("b", (-0., -0., -0.), (1, 2, 3))]
    for body in bodies:
        assert "-0.0" not in json.dumps(body.to_dict())


@pytest.mark.parametrize("bad_id", ["", "with space", "nonascii_ü", "has|separator", None])
def test_all_primitive_ids_use_the_stable_ascii_contract(bad_id):
    factories = [lambda: PlateElement(bad_id, 0, 0, 1, .1),
                 lambda: EndplatePlate(bad_id, 0, 0, 0, 1, 1, .1),
                 lambda: BoxBody(bad_id, (0, 0, 0), (1, 1, 1)),
                 lambda: MeshBody(bad_id, "unused.stl", "0" * 64)]
    for factory in factories:
        with pytest.raises(ValueError, match="ASCII identifier"):
            factory()


def test_mesh_winding_sign_hash_and_mutation(tmp_path):
    path = tmp_path / "box.stl"
    path.write_bytes(trimesh.creation.box(extents=(1, 1, 1)).export(file_type="stl"))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    mesh = MeshBody("fixed", str(path), sha)
    points = np.array([[0, 0, 0], [0.6, 0, 0], [0.6, 0.6, 0], [0.5, 0, 0]])
    np.testing.assert_allclose(mesh.phi(points), [-0.5, 0.1, np.sqrt(0.02), 0], atol=1e-14)
    np.testing.assert_allclose(np.linalg.norm(gradient(mesh, points[1:3]), axis=-1), 1, atol=1e-8)
    assert mesh.to_dict()["parameters"]["sha256"] == sha
    with pytest.raises(ValueError, match="hash|SHA"):
        MeshBody("bad", str(path), "0" * 64)
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash|SHA"):
        mesh.to_dict()
    with pytest.raises(ValueError, match="hash|SHA"):
        mesh.phi(points)


def test_mesh_rejects_open_and_inverted_stl(tmp_path):
    for name, triangles in [("open", trimesh.creation.box().triangles[:-1]),
                            ("inverted", trimesh.creation.box().triangles[:, ::-1])]:
        path = tmp_path / (name + ".stl")
        mesh = trimesh.Trimesh(vertices=triangles.reshape(-1, 3),
                               faces=np.arange(triangles.size // 3).reshape(-1, 3), process=False)
        path.write_bytes(mesh.export(file_type="stl"))
        with pytest.raises(ValueError, match="watertight|winding|volume"):
            MeshBody(name, str(path), hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.mark.parametrize("primitive", [PlateElement("p", 0.1, 0.2, 1, 0.1, angle=0.3, camber=0.03),
                                        EndplatePlate("e", 0, 0, 0, 1, 1, 0.1),
                                        BoxBody("b", (0, 0, 0), (1, 2, 3), 4)])
@pytest.mark.parametrize("dimension", [2, 3])
def test_bounds_boundary_serialization_and_no_input_mutation(primitive, dimension):
    points = primitive.boundary_points(0.15, dimension=dimension)
    copy = points.copy()
    assert points.shape[-1] == dimension
    assert np.max(np.abs(primitive.phi(points))) < 1e-13
    lo, hi = primitive.bbox(dimension)
    assert np.all(points >= lo - 1e-14) and np.all(points <= hi + 1e-14)
    np.testing.assert_array_equal(points, copy)
    assert json.dumps(primitive.to_dict(), sort_keys=True, allow_nan=False) == json.dumps(primitive.to_dict(), sort_keys=True, allow_nan=False)


@pytest.mark.parametrize("changes", [{"id": ""}, {"id": "x y"}, {"chord": 0},
                                      {"thickness": -1}, {"span": 0}, {"angle": np.inf},
                                      {"camber": np.nan}, {"x": True}, {"x": "1"}, {"x": np.complex64(1j)}])
def test_bad_plate_parameters(changes):
    with pytest.raises((TypeError, ValueError)):
        replace(PlateElement("p", 0, 0, 1, 0.1), **changes)


def test_bad_points_and_sampling_parameters():
    p = PlateElement("p", 0, 0, 1, 0.1)
    for points in [np.zeros((2, 4)), np.array([[np.nan, 0]]), np.array([[1j, 0]]), np.zeros(3)]:
        if points.shape == (3,):
            assert np.ndim(p.phi(points)) == 0
        else:
            with pytest.raises(ValueError):
                p.phi(points)
    for dimension in (1, 4, 2.0, True):
        with pytest.raises(ValueError):
            p.bbox(dimension)
    with pytest.raises(ValueError):
        p.boundary_points(0)
    with pytest.raises(ValueError):
        BoxBody("b", (0, 0, 0), (1, 1, 1), 1.5)
    with pytest.raises(ValueError):
        BoxBody("b", (0, 0, 0), (1, -1, 1))
    with pytest.raises(ValueError):
        BoxBody("b", (0, 1j, 0), (1, 1, 1))
