from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import numpy as np
import pytest
import trimesh
import yaml

from cfd_sdf.local_design_mask_memmap import build_local_design_mask_memmaps
from cfd_sdf.local_design_stl_roles import local_design_stl_role_classifier
from cfd_sdf.problem_spec import canonical_local_design_grid, load_problem_spec


def _write_box(path: Path, center: tuple[float, float, float], extents: tuple[float, float, float]) -> None:
    trimesh.creation.box(
        extents=extents,
        transform=trimesh.transformations.translation_matrix(center),
    ).export(path)


def _write_notched_prism(path: Path) -> None:
    """Write one connected watertight L-prism (a box with a corner notch)."""

    polygon = np.array(((0.0, 0.0), (0.02, 0.0), (0.02, 0.01), (0.01, 0.01), (0.01, 0.024), (0.0, 0.024)))
    lower = np.column_stack((polygon, np.zeros(len(polygon))))
    upper = np.column_stack((polygon, np.full(len(polygon), 0.008)))
    vertices = np.vstack((lower, upper))
    top = ((0, 1, 3), (0, 3, 5), (1, 2, 3), (3, 4, 5))
    faces: list[tuple[int, int, int]] = [(c, b, a) for a, b, c in top]
    faces.extend((a + 6, b + 6, c + 6) for a, b, c in top)
    for index in range(len(polygon)):
        next_index = (index + 1) % len(polygon)
        faces.extend(((index, next_index, next_index + 6), (index, next_index + 6, index + 6)))
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.asarray(faces), process=False)
    assert mesh.is_watertight
    if not mesh.is_volume:
        mesh.invert()
    assert mesh.is_volume
    mesh.export(path)


def _generic_contains(mesh: trimesh.Trimesh, points: np.ndarray, tolerance: float) -> np.ndarray:
    _, distances, _ = trimesh.proximity.closest_point(mesh, points)
    assert np.all(distances > tolerance)
    return mesh.contains(points)


def _problem(tmp_path: Path) -> Path:
    """Create a 10 x 12 x 4 local grid with every relevant STL role."""

    data = yaml.safe_load(Path("examples/g2_openfoam_compile/project.yaml").read_text(encoding="utf-8"))
    geometry = tmp_path / "geometry"
    geometry.mkdir(parents=True)
    # Bounds exactly equal the design_domain STL; cell centres are 2 mm apart.
    _write_box(geometry / "design.stl", (0.01, 0.012, 0.004), (0.02, 0.024, 0.008))
    _write_box(geometry / "fixed.stl", (0.003, 0.003, 0.003), (0.003, 0.003, 0.003))
    _write_box(geometry / "root.stl", (0.003, 0.003, 0.003), (0.003, 0.003, 0.003))
    _write_box(geometry / "forbidden.stl", (0.009, 0.003, 0.003), (0.003, 0.003, 0.003))
    _write_box(geometry / "initial.stl", (0.015, 0.003, 0.003), (0.003, 0.003, 0.003))
    data["geometry_regions"] = [
        {"id": "design", "role": "design_domain", "file": "geometry/design.stl"},
        {"id": "fixed", "role": "fixed_solid", "file": "geometry/fixed.stl"},
        {"id": "root", "role": "root", "file": "geometry/root.stl"},
        {"id": "forbidden", "role": "forbidden_region", "file": "geometry/forbidden.stl"},
        {"id": "initial", "role": "initial_design", "file": "geometry/initial.stl"},
    ]
    data["topology_policy"] = deepcopy(data["topology_policy"])
    data["topology_policy"]["root_groups"] = [{"id": "mounts", "region_ids": ["root"]}]
    data["design_grid"] = {
        "kind": "uniform_cartesian",
        "design_domain_region_id": "design",
        "voxel_size_m": 0.002,
        "domain_bounds_m": {"lower": [0.0, 0.0, 0.0], "upper": [0.02, 0.024, 0.008]},
        "expected_cell_shape": [10, 12, 4],
        "expected_cell_count": 480,
        "topology_resolution": {
            "minimum_solid_width_cells": 5,
            "minimum_void_width_cells": 6,
            "minimum_gap_cells": 4,
            "erosion_radius_cells": 2,
        },
    }
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _centres(grid) -> np.ndarray:
    indices = np.arange(grid.cell_count, dtype=np.int64)
    nx, ny, _ = grid.cell_shape
    return np.asarray(grid.origin) + (
        np.column_stack((indices % nx, (indices // nx) % ny, indices // (nx * ny))) + 0.5
    ) * np.asarray(grid.spacing)


def test_stl_role_callback_is_deterministic_and_uses_memmap_derivation(tmp_path: Path) -> None:
    problem = _problem(tmp_path)
    spec = load_problem_spec(problem)
    classifier = local_design_stl_role_classifier(spec, containment_chunk_size=2)
    grid = canonical_local_design_grid(spec)
    points = _centres(grid)

    whole = classifier(points)
    split = {
        name: np.concatenate([classifier(points[:111])[name], classifier(points[111:])[name]])
        for name in whole
    }
    assert all(np.array_equal(whole[name], split[name]) for name in whole)
    assert int(whole["design_domain"].sum()) == grid.cell_count
    assert int(whole["fixed_solid"].sum()) == 1
    assert int(whole["root"].sum()) == 1
    assert int(whole["forbidden_region"].sum()) == 1
    # The initial STL occupies one cell but must have no role-mask effect.
    initial_cell = 7 + 10 * 1 + 10 * 12 * 1
    assert whole["design_domain"][initial_cell]
    assert not any(whole[role][initial_cell] for role in ("fixed_solid", "root", "forbidden_region"))

    artifacts = build_local_design_mask_memmaps(
        grid,
        output_dir=tmp_path / "masks",
        role_containment=classifier.as_role_containment(),
        z_chunk_size=1,
        require_root=True,
    )
    masks = {name: np.load(path, mmap_mode="r") for name, path in artifacts.paths.items()}
    assert artifacts.true_counts == {
        "active_design_mask": grid.cell_count - 2,
        "forbidden_mask": 1,
        "fixed_solid_mask": 1,
        "root_mask": 1,
    }
    assert np.all(masks["root_mask"] <= masks["fixed_solid_mask"])
    assert not np.any(masks["fixed_solid_mask"] & masks["forbidden_mask"])
    assert masks["active_design_mask"][initial_cell]

    metadata = classifier.provenance_metadata
    assert set(metadata) == {"design", "fixed", "root", "forbidden", "initial"}
    assert metadata["initial"]["role"] == "initial_design"
    assert metadata["design"]["relative_source_path"] == "geometry/design.stl"
    assert metadata["design"]["resolved_relative_source_path"] == "geometry/design.stl"
    assert metadata["design"]["bounds_m"]["upper"] == pytest.approx([0.02, 0.024, 0.008])
    assert metadata["design"]["classifier"] == {
        "method": "analytic_aabb",
        "validation": {"status": "accepted", "reason": "strict_aabb_surface"},
        "surface_tolerance_m": pytest.approx(2.0e-13),
        "mesh_counts": {"vertex_count": 8, "face_count": 12, "connected_component_count": 1},
    }
    assert metadata["initial"]["classifier"]["method"] == "not_classified"
    assert metadata["initial"]["classifier"]["validation"] == {
        "status": "not_classified",
        "reason": "initial_design_source_provenance_only",
    }
    assert metadata["design"]["sha256"] == hashlib.sha256(
        (tmp_path / "geometry" / "design.stl").read_bytes()
    ).hexdigest()


def test_rejects_open_declared_stl_before_classification(tmp_path: Path) -> None:
    problem = _problem(tmp_path)
    mesh = trimesh.Trimesh(
        vertices=np.array(((0.0, 0.0, 0.0), (0.001, 0.0, 0.0), (0.0, 0.001, 0.0))),
        faces=np.array(((0, 1, 2),)),
        process=False,
    )
    mesh.export(tmp_path / "geometry" / "forbidden.stl")
    with pytest.raises(ValueError, match="must be watertight"):
        local_design_stl_role_classifier(problem)


def test_rejects_point_on_declared_stl_surface(tmp_path: Path) -> None:
    problem = _problem(tmp_path)
    # Use the parsed STL coordinate rather than a decimal approximation: binary
    # STL stores vertices as float32, while production cell centres are checked
    # against that stored surface with the same tight tolerance as G2 masks.
    _write_box(tmp_path / "geometry" / "forbidden.stl", (0.0045, 0.003, 0.003), (0.003, 0.003, 0.003))
    classifier = local_design_stl_role_classifier(problem)
    lower = trimesh.load_mesh(tmp_path / "geometry" / "forbidden.stl", process=True).bounds[0, 0]
    with pytest.raises(ValueError, match="Containment is ambiguous"):
        classifier(np.array([[lower, 0.003, 0.003]], dtype=np.float64))


def test_accepted_aabb_uses_exact_distance_and_matches_generic_containment(tmp_path: Path) -> None:
    problem = _problem(tmp_path)
    classifier = local_design_stl_role_classifier(problem, containment_chunk_size=2)
    metadata = classifier.provenance_metadata["design"]["classifier"]
    assert metadata["method"] == "analytic_aabb"
    mesh = trimesh.load_mesh(tmp_path / "geometry" / "design.stl", process=True)
    points = np.array(
        (
            (0.001, 0.001, 0.001),  # strict interior
            (0.019, 0.023, 0.007),  # strict interior near the opposite corner
            (-0.001, 0.012, 0.004),  # exterior
            (0.021, 0.012, 0.004),  # exterior
        ),
        dtype=np.float64,
    )
    assert np.array_equal(
        classifier(points)["design_domain"],
        _generic_contains(mesh, points, float(metadata["surface_tolerance_m"])),
    )
    lower_x, upper_x = mesh.bounds[:, 0]
    for surface_point in (
        np.array([[lower_x, 0.012, 0.004]], dtype=np.float64),
        np.array([[lower_x - 1.0e-14, 0.012, 0.004]], dtype=np.float64),
        np.array([[upper_x + 1.0e-14, 0.012, 0.004]], dtype=np.float64),
    ):
        with pytest.raises(ValueError, match="Containment is ambiguous"):
            classifier(surface_point)


@pytest.mark.parametrize("kind", ("rotated", "multiple", "notched"))
def test_noncanonical_box_like_meshes_fall_back_to_generic_classifier(tmp_path: Path, kind: str) -> None:
    problem = _problem(tmp_path)
    # The design-domain STL is bound to the declared local-grid bounds.  Use a
    # fixed role so these deliberately non-box meshes do not invalidate that
    # independent ProblemSpec contract before the classifier is reached.
    target = tmp_path / "geometry" / "fixed.stl"
    if kind == "rotated":
        mesh = trimesh.creation.box(extents=(0.012, 0.012, 0.006))
        rotation = trimesh.transformations.rotation_matrix(np.deg2rad(20.0), (0.0, 0.0, 1.0))
        rotation[:3, 3] = (0.01, 0.012, 0.004)
        mesh.apply_transform(rotation)
        mesh.export(target)
    elif kind == "multiple":
        mesh = trimesh.util.concatenate(
            (
                trimesh.creation.box(extents=(0.004, 0.004, 0.004), transform=trimesh.transformations.translation_matrix((0.004, 0.004, 0.004))),
                trimesh.creation.box(extents=(0.004, 0.004, 0.004), transform=trimesh.transformations.translation_matrix((0.016, 0.02, 0.004))),
            )
        )
        mesh.export(target)
    else:
        _write_notched_prism(target)
    metadata = local_design_stl_role_classifier(problem).provenance_metadata["fixed"]["classifier"]
    assert metadata["method"] == "generic_trimesh"
    assert metadata["validation"]["status"] == "fallback"
    assert metadata["validation"]["reason"] != "strict_aabb_surface"


def test_actual_g2_roles_have_expected_classifier_methods_without_building_large_masks() -> None:
    metadata = local_design_stl_role_classifier("examples/g2_openfoam_compile/project.yaml").provenance_metadata
    assert {identifier: entry["classifier"]["method"] for identifier, entry in metadata.items()} == {
        "vehicle_nose": "analytic_aabb",
        "ground": "analytic_aabb",
        "front_wing_initial": "not_classified",
        "allowed_front_box": "analytic_aabb",
        "tire_clearance": "generic_trimesh",
        "root_mount_left_fixed": "analytic_aabb",
        "root_mount_right_fixed": "analytic_aabb",
        "root_mount_left": "analytic_aabb",
        "root_mount_right": "analytic_aabb",
    }
