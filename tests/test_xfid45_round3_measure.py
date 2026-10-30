"""Synthetic-only Round3 certificates and correspondence regressions."""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from xfid45_round3_measure import distance, fidelity, Field, line_roots


def cube(radius):
    import trimesh

    mesh = trimesh.creation.box(extents=[2 * radius] * 3)
    return np.asarray(mesh.vertices), np.asarray(mesh.faces)


def box_field(radius):
    axis = np.arange(-20, 21) * 0.025
    xyz = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1)
    return np.max(np.abs(xyz), axis=-1) - radius, np.array([-0.5] * 3)


def test_certificates_affine_plane_and_tiny_positive_field():
    h = 0.025
    axis = np.arange(9) * h
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    v = np.array([[0.1, 0.05, 0.05], [0.1, 0.15, 0.05], [0.1, 0.1, 0.15]])
    f = np.array([[0, 1, 2]])
    cert, _ = distance(v, f, x - 0.1, np.zeros(3), h)
    assert cert["within_limit"] and cert["unresolved_sample_count"] == 0
    bad, _ = distance(v + [0.001, 0, 0], f, x - 0.1, np.zeros(3), h)
    assert bad["certified_exceeds_limit"] and not bad["within_limit"]
    tiny, _ = distance(v, f, 1e-200 + 1e-201 * x, np.zeros(3), h)
    assert not tiny["within_limit"] and tiny["unresolved_sample_count"] == 10


def test_normal_surface_correspondence_matches_analytic_box_offset():
    v, f = cube(0.25)
    tv, tf = cube(0.255)
    base, o = box_field(0.25)
    target, _ = box_field(0.255)
    report, samples = fidelity(v, f, tv, tf, base, target, o, 0.025)
    assert report["within_limit"]
    np.testing.assert_allclose(samples[:, 6], 0.005, atol=1e-12)
    np.testing.assert_allclose(samples[:, 7], 0.005, atol=1e-12)
    wrong, _ = fidelity(v, f, *cube(0.257), base, target, o, 0.025)
    assert not wrong["within_limit"]


def test_zero_interval_is_not_a_unique_surface_correspondence():
    field = Field(np.zeros((5, 5, 5)), np.zeros(3), 0.025)
    root, audit = line_roots(field, np.array([0.05] * 3), np.array([1.0, 0, 0]), 0.025)
    assert root is None and audit["zero_interval"]


def test_step0_independent_topology_orientation_and_serialization_contract():
    """All retained faces, edge connectivity and vertex links agree before freeze."""
    from xfid45_round3_export import topology, orient
    from verify_xfid45_round3 import topology as independent_topology, orientation
    from audit_xfid45_surface_round3 import stored_orientation
    import trimesh
    import io

    v, f = cube(0.25)
    deg_v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
    deg_f = np.array([[0, 1, 2], [0, 0, 1]])
    edge_v = np.vstack((deg_v, [[0, -1, 0], [0, 0, 1]]))
    edge_f = np.array([[0, 1, 2], [1, 0, 3], [0, 1, 4]])
    # Two closed cubes sharing precisely one vertex: edge-connected components two.
    pv = np.vstack((v, v + 0.5))
    pf = np.vstack((f, f + len(v)))
    collapse_v = np.array([[1, 0, 0], [1 + 1e-8, 0, 0], [0, 1, 0]], dtype=float)
    cases = [
        ("degenerate", deg_v, deg_f),
        ("nonmanifold_edge", edge_v, edge_f),
        ("pinched_vertex", pv, pf),
        ("float32_collapse", collapse_v, np.array([[0, 1, 2]])),
    ]
    phi, o = box_field(0.25)
    for name, vertices, faces in cases:
        for serialized in (False, True):
            if serialized:
                raw = trimesh.Trimesh(vertices, faces, process=False).export(
                    file_type="stl"
                )
                mesh = trimesh.load(io.BytesIO(raw), file_type="stl", process=False)
                vertices, faces = np.array(mesh.vertices), np.array(mesh.faces)
            a = topology(vertices, faces)
            b = independent_topology(vertices, faces)
            keys = [
                "edge_connected_component_count",
                "component_min_original_face_id",
                "edge_incidence_not_two_count",
                "vertex_link_bad_count",
                "watertight",
                "winding_consistent",
                "duplicate_face_count",
                "repeated_index_face_count",
                "zero_area_face_count",
                "topology_pass",
                "stage_v_clearance_pass",
            ]
            assert all(a[k] == b[k] for k in keys), (name, serialized, a, b)
            oriented, audit = orient(vertices, faces, phi, o, 0.025)
            independent = orientation(vertices, faces, phi, o, 0.025)
            assert audit["status"] == independent["status"] == "N/A"
            assert np.array_equal(oriented, faces)
    # Void normal points into fluid cavity; inward stored outer surface must fail.
    axis = np.arange(-32, 33) * 0.025
    xyz = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1)
    hollow = np.maximum(
        np.max(np.abs(xyz), axis=-1) - 0.5, 0.25 - np.max(np.abs(xyz), axis=-1)
    )
    ov, of = cube(0.5)
    iv, inf = cube(0.25)
    vertices = np.vstack((ov, iv))
    faces = np.vstack((of, inf + len(ov)))
    oriented, _ = orient(vertices, faces, hollow, np.array([-0.8] * 3), 0.025)
    for faces in (oriented, oriented[:, [0, 2, 1]]):
        a = stored_orientation(vertices, faces, hollow, np.array([-0.8] * 3), 0.025)
        b = orientation(vertices, faces, hollow, np.array([-0.8] * 3), 0.025)
        assert a["status"] == b["status"]
    assert b["status"] == "FAIL"


def test_step0_independent_distance_fidelity_and_volume_agree():
    from verify_xfid45_round3 import distance as independent_distance
    from verify_xfid45_round3 import fidelity as independent_fidelity
    from verify_xfid45_round3 import volume as independent_volume
    from xfid45_round3_measure import volume

    v, f = cube(0.25)
    tv, tf = cube(0.255)
    base, o = box_field(0.25)
    target, _ = box_field(0.255)
    for vv in (v, v * 1.01):
        a, _ = distance(vv, f, base, o, 0.025)
        b, _ = independent_distance(vv, f, base, o, 0.025)
        assert a["within_limit"] == b["within_limit"]
        assert a["certified_exceeds_limit"] == b["certified_exceeds_limit"]
    a, _ = fidelity(v, f, tv, tf, base, target, o, 0.025)
    b = independent_fidelity(v, f, tv, tf, base, target, o, 0.025)
    assert a["within_limit"] and b["within_limit"]
    for n in (16, 32, 64):
        assert np.isclose(
            volume(base, o, 0.025, n),
            independent_volume(base, o, 0.025, n),
            rtol=1e-8,
            atol=0.025**3 * 1e-9,
        )


def test_independent_verifier_has_no_extractor_or_evaluator_imports():
    import ast

    root = Path(__file__).resolve().parents[1]
    forbidden = {
        "xfid45_round3_export",
        "xfid45_round3_measure",
        "audit_xfid45_surface_round3",
        "xfid45_surface_round2_candidates",
        "audit_xfid45_surface_round2",
    }
    for filename in ("verify_xfid45_round3.py", "verify_xfid45_surface_round3.py"):
        tree = ast.parse((root / "scripts" / filename).read_text())
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        imports.update(
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
        )
        assert not (imports & forbidden)
