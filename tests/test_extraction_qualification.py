"""Tests for the quantitative extraction qualification (PQ4)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.extraction_qualification import (
    EXTRACTION_QUALIFICATION_PROFILE_V1,
    ExtractionQualificationError,
    qualify_extraction,
)
from cfd_sdf.fixed_grid_contract import CartesianCellGrid, _write_cell_vti
from cfd_sdf.handoff import build_density_to_sdf_handoff


def _write_state(
    directory: Path,
    *,
    cell_shape: tuple[int, int, int] = (6, 6, 6),
    solid_box: tuple = ((1, 4), (1, 4), (1, 4)),
    root_cell: tuple[int, int, int] = (1, 3, 3),
) -> Path:
    from test_handoff import _cell_index, _state_dict

    directory.mkdir(parents=True, exist_ok=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=cell_shape
    )
    count = grid.cell_count
    density = np.zeros(count, dtype=np.float32)
    for x in range(solid_box[0][0], solid_box[0][1] + 1):
        for y in range(solid_box[1][0], solid_box[1][1] + 1):
            for z in range(solid_box[2][0], solid_box[2][1] + 1):
                density[_cell_index((x, y, z), cell_shape)] = 1.0
    root = np.zeros(count, dtype=np.uint8)
    if root_cell is not None:
        root[_cell_index(root_cell, cell_shape)] = 1
    arrays = {
        "rho": density,
        "rho_filtered": density.copy(),
        "rho_projected": density.copy(),
        "alpha": density.copy(),
        "allowed_mask": np.ones(count, dtype=np.uint8),
        "forbidden_mask": np.zeros(count, dtype=np.uint8),
        "fixed_solid_mask": np.zeros(count, dtype=np.uint8),
        "root_mask": root,
        "active_design_mask": np.ones(count, dtype=np.uint8),
    }
    _write_cell_vti(grid, arrays, directory / "density.vti", kind="fixed_grid_density")
    path = directory / "topology_state.json"
    path.write_text(json.dumps(_state_dict(grid, "density.vti"), indent=2), encoding="utf-8")
    return path


def _handoff(tmp_path: Path, **state_kwargs):
    state = _write_state(tmp_path / "candidate", **state_kwargs)
    return build_density_to_sdf_handoff(state, output_dir=tmp_path / "handoff", iso_value=0.5)


# the unit fixture uses 1 m voxels; scale the registered distances accordingly
TEST_PROFILE = dict(
    EXTRACTION_QUALIFICATION_PROFILE_V1,
    surface_distance_max_m=1.5,
    surface_distance_rms_max_m=1.5,
)


def test_clean_block_passes_the_quantitative_gates(tmp_path: Path):
    artifacts = _handoff(tmp_path)
    result = qualify_extraction(
        artifacts.manifest_json, mesh_path=artifacts.surface_stl, profile=TEST_PROFILE
    )
    assert result.ready_for_stage_s is True, result.reasons
    checks = result.checks
    assert checks["surface_distance"]["status"] == "measured"
    assert checks["mesh_manifold"]["watertight"] is True
    assert checks["mesh_manifold"]["duplicate_face_count"] == 0
    assert checks["root_connectivity"]["status"] == "pass"


def test_impossible_surface_distance_profile_fails(tmp_path: Path):
    artifacts = _handoff(tmp_path)
    profile = dict(
        EXTRACTION_QUALIFICATION_PROFILE_V1,
        surface_distance_max_m=0.0,
        surface_distance_rms_max_m=0.0,
    )
    result = qualify_extraction(
        artifacts.manifest_json, mesh_path=artifacts.surface_stl, profile=profile
    )
    assert result.ready_for_stage_s is False
    assert "surface_distance_exceeds_profile" in result.reasons


def test_unattached_root_component_fails(tmp_path: Path):
    # the handoff refuses a root mask outside the material, so build the two
    # density VTIs directly: two material blobs, the root inside only one
    import trimesh

    grid = CartesianCellGrid(origin=(0, 0, 0), spacing=(1, 1, 1), cell_shape=(8, 4, 4))
    count = grid.cell_count
    revox = np.zeros(count, dtype=np.uint8)
    source = np.zeros(count, dtype=np.float32)
    root = np.zeros(count, dtype=np.uint8)

    def set_box(array, value, x0, x1, y0=1, y1=2, z0=1, z1=2):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    array[x + 8 * (y + 4 * z)] = value

    set_box(revox, 1, 1, 2)
    set_box(revox, 1, 5, 6)
    set_box(source, 1.0, 1, 2)
    set_box(source, 1.0, 5, 6)
    set_box(root, 1, 1, 1, 1, 1, 1, 1)  # inside the first blob only

    handoff = tmp_path / "manual"
    handoff.mkdir(parents=True)
    revox_path = handoff / "rev.vti"
    source_path = handoff / "src.vti"
    _write_cell_vti(grid, {"rho_revoxelized": revox}, revox_path, kind="stage_s_revoxelized_density")
    _write_cell_vti(
        grid,
        {"rho": source, "root_mask": root},
        source_path,
        kind="fixed_grid_density",
    )
    from cfd_sdf.extraction_qualification import _sha256

    manifest = {
        "kind": "density_to_sdf_handoff",
        "rho": {"iso_value": 0.5},
        "artifacts": {
            "revoxelized_density_vti": {"path": "rev.vti", "sha256": _sha256(revox_path)},
            "source_density_vti": {"path": "src.vti", "sha256": _sha256(source_path)},
        },
    }
    manifest_path = handoff / "handoff_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    mesh_path = handoff / "mesh.stl"
    trimesh.creation.box(extents=(2.0, 2.0, 2.0)).export(mesh_path)

    result = qualify_extraction(manifest_path, mesh_path=mesh_path, profile=TEST_PROFILE)
    assert result.ready_for_stage_s is False
    assert "root_connectivity_unattached_component" in result.reasons
    assert result.checks["root_connectivity"]["components"] == 2


def test_empty_root_mask_is_not_applicable_not_passed_silently(tmp_path: Path):
    artifacts = _handoff(tmp_path, root_cell=None)
    result = qualify_extraction(
        artifacts.manifest_json, mesh_path=artifacts.surface_stl, profile=TEST_PROFILE
    )
    assert result.checks["root_connectivity"]["status"] == "not_applicable"
    assert result.ready_for_stage_s is True  # the other gates pass


def test_manifest_tamper_is_rejected(tmp_path: Path):
    artifacts = _handoff(tmp_path)
    document = json.loads(artifacts.manifest_json.read_text(encoding="utf-8"))
    document["artifacts"]["revoxelized_density_vti"]["sha256"] = "0" * 64
    tampered = tmp_path / "handoff" / "tampered_manifest.json"
    tampered.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ExtractionQualificationError, match="changed after the handoff"):
        qualify_extraction(tampered, mesh_path=artifacts.surface_stl)
