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


def test_measured_self_intersection_gates_the_profile_fail_closed():
    from cfd_sdf.extraction_qualification import (
        EXTRACTION_QUALIFICATION_PROFILE_V1,
        _manifold_reasons,
    )

    manifold = {
        "watertight": True,
        "winding_consistent": True,
        "positive_volume": True,
        "duplicate_face_count": 0,
        "non_manifold_edge_count": 0,
        "self_intersection": "fail",
    }
    reasons = _manifold_reasons(manifold, EXTRACTION_QUALIFICATION_PROFILE_V1)
    assert "mesh_self_intersects" in reasons

    clean = {**manifold, "self_intersection": "pass"}
    assert _manifold_reasons(clean, EXTRACTION_QUALIFICATION_PROFILE_V1) == []

    not_evaluated = {**manifold, "self_intersection": "not_evaluated"}
    reasons = _manifold_reasons(not_evaluated, EXTRACTION_QUALIFICATION_PROFILE_V1)
    assert any(reason.startswith("self_intersection:") for reason in reasons)


def _exact_tri_tri_intersects(A, B) -> bool:
    """Reference Möller–Trumbore segment-triangle test (both directions)."""

    import numpy as np

    for P, Q in ((A, B), (B, A)):
        for e in range(3):
            p0, p1 = P[e], P[(e + 1) % 3]
            d = p1 - p0
            e1 = Q[1] - Q[0]
            e2 = Q[2] - Q[0]
            h = np.cross(d, e2)
            a = float(np.dot(e1, h))
            if abs(a) < 1e-14:
                continue
            s = p0 - Q[0]
            u = float(np.dot(s, h)) / a
            if not 0.0 <= u <= 1.0:
                continue
            q = np.cross(s, e1)
            v = float(np.dot(d, q)) / a
            if v < 0.0 or u + v > 1.0:
                continue
            t = float(np.dot(e2, q)) / a
            if 0.0 <= t <= 1.0:
                return True
    return False


def test_edge_pierce_detector_matches_exact_moller_trumbore():
    import numpy as np

    from cfd_sdf.extraction_qualification import _edges_pierce_triangles

    rng = np.random.default_rng(20260923)
    frm = rng.uniform(-1.0, 1.0, (150, 3, 3))
    to = rng.uniform(-1.0, 1.0, (150, 3, 3))
    # half the pairs are translations of each other, so genuine crossings occur
    to[:75] = frm[:75] + rng.normal(0.0, 0.35, (75, 1, 3))
    got = _edges_pierce_triangles(frm, to) | _edges_pierce_triangles(to, frm)
    expected = np.array(
        [_exact_tri_tri_intersects(a, b) for a, b in zip(frm, to, strict=True)]
    )
    mismatches = int(np.count_nonzero(got != expected))
    assert mismatches == 0, f"{mismatches} mismatches against the exact reference"


def test_known_crossing_pair_is_flagged_and_near_parallel_pair_is_not():
    import numpy as np

    from cfd_sdf.extraction_qualification import _edges_pierce_triangles

    a = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]])
    crossing = np.array([[[0.2, 0.2, -0.5], [0.2, 0.2, 0.5], [0.8, 0.5, 0.0]]])
    assert bool(_edges_pierce_triangles(a, crossing)[0]) is True
    assert bool(_edges_pierce_triangles(crossing, a)[0]) is True
    # nearly parallel, non-crossing: the old formula reported this as a hit
    near_parallel = np.array([[[0.0, 0.0, 1e-6], [1.0, 0.0, 1.2e-6], [0.0, 1.0, 0.8e-6]]])
    assert bool(_edges_pierce_triangles(a, near_parallel)[0]) is False
