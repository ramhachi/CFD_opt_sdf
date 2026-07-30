from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from cfd_sdf.local_initial_design_rho import (
    _resolve_surface_point,
    _unique_nearest_face,
    build_local_initial_design_rho_raw,
)
from cfd_sdf.localized_design_state_manifest import LocalizedDesignGrid


def _grid(*, shape: tuple[int, int, int] = (1, 1, 1)) -> LocalizedDesignGrid:
    return LocalizedDesignGrid(
        origin=(0.0, 0.0, 0.0),
        spacing=(1.0, 1.0, 1.0),
        cell_shape=shape,
    )


def _cube(center: tuple[float, float, float], extent: float = 0.12) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=(extent, extent, extent))
    mesh.apply_translation(center)
    return mesh


def _write_mesh(path: Path, meshes: list[trimesh.Trimesh]) -> Path:
    mesh = trimesh.util.concatenate(meshes)
    mesh.export(path)
    return path


def _rho(path: Path) -> np.ndarray:
    return np.asarray(np.load(path, allow_pickle=False))


@pytest.mark.parametrize("inside_count", range(9))
def test_direct_occupancy_has_exact_eighth_fractions(tmp_path: Path, inside_count: int) -> None:
    # qz -> qy -> qx, matching the declared sampler ordering.
    offsets = [(qx, qy, qz) for qz in (0.25, 0.75) for qy in (0.25, 0.75) for qx in (0.25, 0.75)]
    meshes = [_cube(offset) for offset in offsets[:inside_count]]
    if not meshes:
        meshes = [_cube((1.5, 1.5, 1.5))]
    stl = _write_mesh(tmp_path / f"fraction-{inside_count}.stl", meshes)
    artifacts = build_local_initial_design_rho_raw(
        grid=_grid(),
        active_design_mask=np.array([True], dtype=np.bool_),
        initial_design_stl=stl,
        output_dir=tmp_path / f"out-{inside_count}",
        expected_component_count=len(meshes),
        z_chunk_size=1,
        point_chunk_size=1,
    )
    assert _rho(artifacts.rho_raw_path) == pytest.approx([inside_count / 8.0])
    assert artifacts.manifest.occupancy_volume_m3 == pytest.approx(inside_count / 8.0)
    assert artifacts.manifest.subcell_offsets == tuple(offsets)


def test_default_ten_component_front_wing_contract_is_a_union(tmp_path: Path) -> None:
    offsets = [(qx, qy, qz) for qz in (0.25, 0.75) for qy in (0.25, 0.75) for qx in (0.25, 0.75)]
    stl = _write_mesh(
        tmp_path / "ten-components.stl",
        [_cube(offset) for offset in offsets] + [_cube((2.0, 2.0, 2.0)), _cube((3.0, 3.0, 3.0))],
    )
    artifacts = build_local_initial_design_rho_raw(
        grid=_grid(),
        active_design_mask=np.array([True], dtype=np.bool_),
        initial_design_stl=stl,
        output_dir=tmp_path / "out",
    )
    assert _rho(artifacts.rho_raw_path) == pytest.approx([1.0])
    assert artifacts.manifest.component_count == 10
    raw = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert raw["role"] == "initial_design"
    assert raw["method"] == "direct_stl_union_occupancy_2x2x2"
    assert raw["grid_sha256"] == _grid().sha256
    assert len(raw["active_design_mask_sha256"]) == 64


def test_output_is_chunk_invariant_and_exactly_zero_outside_active_mask(tmp_path: Path) -> None:
    grid = _grid(shape=(2, 2, 2))
    stl = _write_mesh(tmp_path / "all-solid.stl", [_cube((1.0, 1.0, 1.0), extent=2.0)])
    active = np.array([True, False, False, True, True, False, True, False], dtype=np.bool_)
    first = build_local_initial_design_rho_raw(
        grid=grid,
        active_design_mask=active,
        initial_design_stl=stl,
        output_dir=tmp_path / "out-a",
        expected_component_count=1,
        z_chunk_size=1,
        point_chunk_size=1,
    )
    second = build_local_initial_design_rho_raw(
        grid=grid,
        active_design_mask=active,
        initial_design_stl=stl,
        output_dir=tmp_path / "out-b",
        expected_component_count=1,
        z_chunk_size=2,
        point_chunk_size=7,
    )
    first_values = _rho(first.rho_raw_path)
    second_values = _rho(second.rho_raw_path)
    assert np.array_equal(first_values, second_values)
    assert np.all(first_values[active] == 1.0)
    assert np.all(first_values[~active] == 0.0)
    assert first.manifest.rho_raw_sha256 == second.manifest.rho_raw_sha256
    assert first.manifest.active_design_mask_sha256 == second.manifest.active_design_mask_sha256


def test_rejects_nonwatertight_and_unsupported_nested_components(tmp_path: Path) -> None:
    open_box = _cube((0.5, 0.5, 0.5), extent=0.4)
    open_box.update_faces(np.arange(len(open_box.faces) - 1))
    open_box.remove_unreferenced_vertices()
    open_stl = _write_mesh(tmp_path / "open.stl", [open_box])
    with pytest.raises(ValueError, match="watertight"):
        build_local_initial_design_rho_raw(
            grid=_grid(),
            active_design_mask=np.array([True], dtype=np.bool_),
            initial_design_stl=open_stl,
            output_dir=tmp_path / "open-out",
            expected_component_count=1,
        )

    nested_stl = _write_mesh(
        tmp_path / "nested.stl",
        [_cube((0.5, 0.5, 0.5), extent=0.8), _cube((0.5, 0.5, 0.5), extent=0.2)],
    )
    with pytest.raises(ValueError, match="unsupported nested"):
        build_local_initial_design_rho_raw(
            grid=_grid(),
            active_design_mask=np.array([True], dtype=np.bool_),
            initial_design_stl=nested_stl,
            output_dir=tmp_path / "nested-out",
            expected_component_count=2,
        )


def _face_interior_surface_box() -> trimesh.Trimesh:
    # x=0.25 passes through exactly one q sample.  Its y/z ranges make that
    # sample strictly interior to one triangle rather than the quad diagonal.
    return trimesh.creation.box(bounds=np.array(((0.25, 0.15, 0.15), (0.60, 0.35, 0.45))))


def test_face_interior_surface_sample_gets_half_contribution_and_v2_evidence(tmp_path: Path) -> None:
    stl = _write_mesh(tmp_path / "surface.stl", [_face_interior_surface_box()])
    artifacts = build_local_initial_design_rho_raw(
        grid=_grid(),
        active_design_mask=np.array([True], dtype=np.bool_),
        initial_design_stl=stl,
        output_dir=tmp_path / "surface-out",
        expected_component_count=1,
    )
    assert _rho(artifacts.rho_raw_path) == pytest.approx([1.0 / 16.0])
    resolution = artifacts.manifest.surface_resolution
    assert resolution.kind == "symmetric_normal_offset_union"
    assert resolution.surface_tolerance_m == 1.0e-9
    assert resolution.normal_offset_m == 1.0e-6
    assert resolution.tie_point_count == 1
    assert dict(resolution.contribution_counts) == {"zero": 0, "half": 1, "one": 0}
    raw = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert raw["surface_resolution"]["sampler_implementation"] == "cfd_sdf.local_initial_design_rho"
    assert raw["surface_resolution"]["sampler_version"] == 2


def test_surface_resolution_is_invariant_to_flipped_winding_and_offset_scale(tmp_path: Path) -> None:
    normal = _face_interior_surface_box()
    flipped = normal.copy()
    flipped.invert()
    normal_stl = _write_mesh(tmp_path / "normal.stl", [normal])
    flipped_stl = _write_mesh(tmp_path / "flipped.stl", [flipped])
    first = build_local_initial_design_rho_raw(
        grid=_grid(), active_design_mask=np.array([True], dtype=np.bool_), initial_design_stl=normal_stl,
        output_dir=tmp_path / "normal-out", expected_component_count=1,
    )
    second = build_local_initial_design_rho_raw(
        grid=_grid(), active_design_mask=np.array([True], dtype=np.bool_), initial_design_stl=flipped_stl,
        output_dir=tmp_path / "flipped-out", expected_component_count=1,
    )
    assert np.array_equal(_rho(first.rho_raw_path), _rho(second.rho_raw_path))

    point = np.array((0.25, 0.25, 0.25), dtype=np.float64)
    assert [_resolve_surface_point((normal,), point, normal_offset_m=value) for value in (0.5e-6, 1.0e-6, 2.0e-6)] == [0.5, 0.5, 0.5]


def test_surface_resolution_is_chunk_invariant_and_skips_nonactive_cells(tmp_path: Path) -> None:
    stl = _write_mesh(tmp_path / "surface-chunks.stl", [_face_interior_surface_box()])
    grid = _grid(shape=(1, 1, 2))
    active = np.array((True, False), dtype=np.bool_)
    first = build_local_initial_design_rho_raw(
        grid=grid, active_design_mask=active, initial_design_stl=stl,
        output_dir=tmp_path / "surface-chunks-a", expected_component_count=1,
        z_chunk_size=1, point_chunk_size=1,
    )
    second = build_local_initial_design_rho_raw(
        grid=grid, active_design_mask=active, initial_design_stl=stl,
        output_dir=tmp_path / "surface-chunks-b", expected_component_count=1,
        z_chunk_size=2, point_chunk_size=16,
    )
    assert np.array_equal(_rho(first.rho_raw_path), _rho(second.rho_raw_path))
    assert _rho(first.rho_raw_path).tolist() == pytest.approx([1.0 / 16.0, 0.0])


def test_surface_resolution_rejects_edges_vertices_multiple_faces_and_uncleared_offsets() -> None:
    box = _face_interior_surface_box()
    with pytest.raises(ValueError):
        _resolve_surface_point((box,), np.array((0.25, 0.15, 0.25)))
    with pytest.raises(ValueError):
        _resolve_surface_point((box,), np.array((0.25, 0.15, 0.15)))
    with pytest.raises(ValueError, match="unique nearest face"):
        _resolve_surface_point((box, box.copy()), np.array((0.25, 0.25, 0.25)))

    point = np.array((0.25, 0.25, 0.25), dtype=np.float64)
    component, face_index, _ = _unique_nearest_face((box,), point)
    triangle = component.triangles[face_index]
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    normal /= np.linalg.norm(normal)
    target = point + normal * 1.0e-6
    axis = int(np.argmax(np.abs(normal)))
    lower = target - np.array((0.01, 0.01, 0.01))
    upper = target + np.array((0.01, 0.01, 0.01))
    if normal[axis] > 0.0:
        lower[axis] = target[axis]
    else:
        upper[axis] = target[axis]
    obstacle = trimesh.creation.box(bounds=np.stack((lower, upper)))
    with pytest.raises(ValueError, match="remains on a surface"):
        _resolve_surface_point((box, obstacle), point)


def test_focused_real_front_wing_top_plane_ties_resolve_without_full_grid_build(tmp_path: Path) -> None:
    # z=.3125 is the actual q=.25 local-grid plane that stopped the first
    # full build.  This one-cell diagnostic exercises four planar tie points
    # against the unchanged ten-component front-wing STL.
    root = Path(__file__).resolve().parents[1]
    stl = root / "examples/front_wing/geometry/front_wing_initial.stl"
    grid = LocalizedDesignGrid(
        origin=(0.599, -0.001, 0.312), spacing=(0.002, 0.002, 0.002), cell_shape=(1, 1, 1)
    )
    artifacts = build_local_initial_design_rho_raw(
        grid=grid,
        active_design_mask=np.array([True], dtype=np.bool_),
        initial_design_stl=stl,
        output_dir=tmp_path / "front-wing-top-plane",
        expected_component_count=10,
    )
    resolution = artifacts.manifest.surface_resolution
    assert resolution.tie_point_count > 0
    assert sum(resolution.contribution_counts.values()) == resolution.tie_point_count
    assert resolution.contribution_counts["half"] > 0


def test_wrong_component_contract_is_rejected(tmp_path: Path) -> None:

    stl = _write_mesh(tmp_path / "single.stl", [_cube((0.5, 0.5, 0.5))])
    with pytest.raises(ValueError, match="component count"):
        build_local_initial_design_rho_raw(
            grid=_grid(),
            active_design_mask=np.array([True], dtype=np.bool_),
            initial_design_stl=stl,
            output_dir=tmp_path / "wrong-component-count",
        )


def test_inactive_cell_on_source_surface_is_not_queried(tmp_path: Path) -> None:
    # This is the same surface-crossing source as above.  The local topology
    # contract excludes this cell, so it must write an exact zero rather than
    # fail a geometric query that is irrelevant to rho_raw.
    surface = trimesh.creation.box(extents=(0.35, 0.8, 0.8))
    surface.apply_translation((0.425, 0.5, 0.5))
    stl = _write_mesh(tmp_path / "inactive-surface.stl", [surface])
    artifacts = build_local_initial_design_rho_raw(
        grid=_grid(),
        active_design_mask=np.array([False], dtype=np.bool_),
        initial_design_stl=stl,
        output_dir=tmp_path / "inactive-surface-out",
        expected_component_count=1,
    )
    assert _rho(artifacts.rho_raw_path).tolist() == [0.0]
