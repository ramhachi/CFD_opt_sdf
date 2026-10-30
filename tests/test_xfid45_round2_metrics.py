"""Synthetic measurement tests; never evaluate registered target inputs."""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np
from xfid45_round2_metrics import displacement, mesh_stats


def test_sampled_identity_certificates_for_affine_zero_plane():
    h = 0.025
    axis = np.arange(9) * h
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    phi = x - 0.1
    v = np.array([[0.1, 0.05, 0.05], [0.1, 0.15, 0.05], [0.1, 0.1, 0.15]])
    result, _ = displacement(v, np.array([[0, 1, 2]]), phi, np.zeros(3), h)
    assert result["within_displacement_limit"]
    assert result["maximum_certified_upper_distance_m"] < 1e-14
    moved = v + np.array([0.001, 0, 0])
    result, _ = displacement(moved, np.array([[0, 1, 2]]), phi, np.zeros(3), h)
    assert result["certified_exceeds_limit"]
    assert not result["within_displacement_limit"]


def test_closed_tetrahedron_has_manifold_vertex_links():
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    f = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
    stats = mesh_stats(v, f)
    assert stats["watertight"] and stats["winding_consistent"]
    assert stats["nonmanifold_vertex_links"] == 0
    bad = mesh_stats(np.concatenate([v, v + [0, 0, 0]]), np.concatenate([f, f + 4]))
    assert bad["nonmanifold_edges"] > 0


def test_independent_verifier_does_not_import_extraction_or_measurement_modules():
    path = (
        Path(__file__).resolve().parents[1] / "scripts/verify_xfid45_surface_round2.py"
    )
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names] + (
                [node.module] if isinstance(node, ast.ImportFrom) else []
            )
            assert not any(
                name
                and (
                    "candidates" in name
                    or "round2_metrics" in name
                    or "audit_xfid45" in name
                )
                for name in names
            )


def test_tiny_everywhere_positive_field_cannot_create_root_by_underflow():
    from verify_xfid45_surface_round2 import independent_identity

    h = 0.025
    axis = np.arange(9) * h
    x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
    phi = 1e-200 + 1e-201 * x
    v = np.array([[0.0001, 0.05, 0.05], [0.0001, 0.15, 0.05], [0.0001, 0.1, 0.15]])
    f = np.array([[0, 1, 2]])
    result, _ = displacement(v, f, phi, np.zeros(3), h)
    check = independent_identity(v, f, phi, np.zeros(3), h)
    assert not result["within_displacement_limit"]
    assert result["unresolved_sample_count"] == 10
    assert not check["within_displacement_limit"]
    assert check["unresolved_sample_count"] == 10
