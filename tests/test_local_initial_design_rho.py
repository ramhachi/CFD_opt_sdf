from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from cfd_sdf.local_initial_design_rho import build_local_initial_design_rho_raw
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


def test_rejects_surface_samples_and_wrong_component_contract(tmp_path: Path) -> None:
    # The first q point lies on x=0.25, so assigning it in or out is forbidden.
    surface = trimesh.creation.box(extents=(0.35, 0.8, 0.8))
    surface.apply_translation((0.425, 0.5, 0.5))
    surface_stl = _write_mesh(tmp_path / "surface.stl", [surface])
    with pytest.raises(ValueError, match="on the STL surface"):
        build_local_initial_design_rho_raw(
            grid=_grid(),
            active_design_mask=np.array([True], dtype=np.bool_),
            initial_design_stl=surface_stl,
            output_dir=tmp_path / "surface-out",
            expected_component_count=1,
        )

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
