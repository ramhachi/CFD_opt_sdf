from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
import yaml

import cfd_sdf.local_design_geometry_snapshot as geometry_snapshot_module
from cfd_sdf.local_design_geometry_snapshot import (
    LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME,
    create_local_design_geometry_mask_snapshot,
    load_and_verify_local_design_geometry_mask_snapshot,
    read_local_design_geometry_mask_snapshot,
)
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256


def _write_box(path: Path, center: tuple[float, float, float], extents: tuple[float, float, float]) -> None:
    trimesh.creation.box(
        extents=extents,
        transform=trimesh.transformations.translation_matrix(center),
    ).export(path)


def _problem(tmp_path: Path) -> Path:
    data = yaml.safe_load(Path("examples/g2_openfoam_compile/project.yaml").read_text(encoding="utf-8"))
    geometry = tmp_path / "geometry"
    geometry.mkdir()
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


def test_creates_portable_verified_geometry_only_snapshot_from_tiny_stls(tmp_path: Path) -> None:
    problem = _problem(tmp_path)
    output = tmp_path / "snapshot"
    verified = create_local_design_geometry_mask_snapshot(
        problem, output_dir=output, z_chunk_size=1, containment_chunk_size=2
    )
    snapshot = verified.snapshot

    assert snapshot.path == output / LOCAL_DESIGN_GEOMETRY_SNAPSHOT_FILENAME
    assert snapshot.grid.cell_count == 480
    assert snapshot.topology_resolution == {
        "minimum_solid_width_cells": 5,
        "minimum_void_width_cells": 6,
        "minimum_gap_cells": 4,
        "erosion_radius_cells": 2,
    }
    assert set(snapshot.masks) == {"active_design_mask", "forbidden_mask", "fixed_solid_mask", "root_mask"}
    assert snapshot.masks["active_design_mask"].relative_path == "masks/active_design_mask.npy"
    assert snapshot.masks["root_mask"].true_count == 1
    assert snapshot.classifier_regions["initial"]["role"] == "initial_design"
    assert snapshot.classifier_regions["design"]["sha256"] == hashlib.sha256(
        (tmp_path / "geometry" / "design.stl").read_bytes()
    ).hexdigest()
    assert snapshot.problem_spec_sha256 == problem_spec_sha256(load_problem_spec(problem))

    masks = {identifier: np.load(output / artifact.relative_path, mmap_mode="r") for identifier, artifact in snapshot.masks.items()}
    assert int(masks["active_design_mask"].sum()) == 478
    assert not np.any(masks["active_design_mask"] & masks["forbidden_mask"])
    assert np.all(~masks["root_mask"] | masks["fixed_solid_mask"])
    assert load_and_verify_local_design_geometry_mask_snapshot(snapshot.path).snapshot.sha256 == snapshot.sha256


def test_tampering_or_manifest_path_escape_is_refused(tmp_path: Path) -> None:
    snapshot = create_local_design_geometry_mask_snapshot(_problem(tmp_path), output_dir=tmp_path / "snapshot").snapshot
    root_path = snapshot.path.parent / snapshot.masks["root_mask"].relative_path
    values = np.load(root_path)
    values[0] = True
    np.save(root_path, values)
    with pytest.raises(ValueError, match="hash mismatch: root_mask"):
        load_and_verify_local_design_geometry_mask_snapshot(snapshot.path)

    # Make the manifest's structure hostile separately; artifact hash mismatch
    # must not mask a traversal attempt in the parser.
    raw = json.loads(snapshot.path.read_text(encoding="utf-8"))
    raw["masks"]["root_mask"]["relative_path"] = "../outside.npy"
    snapshot.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="safe relative path"):
        read_local_design_geometry_mask_snapshot(snapshot.path)


def test_existing_output_is_immutable_and_never_partially_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "snapshot"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("immutable", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        create_local_design_geometry_mask_snapshot(_problem(tmp_path), output_dir=output)
    assert sentinel.read_text(encoding="utf-8") == "immutable"


def test_verification_scans_mask_relationships_in_bounded_synchronized_chunks(tmp_path: Path, monkeypatch) -> None:
    snapshot = create_local_design_geometry_mask_snapshot(_problem(tmp_path), output_dir=tmp_path / "snapshot").snapshot
    monkeypatch.setattr(geometry_snapshot_module, "_CHUNK_CELLS", 2)
    original_any = np.any

    def reject_full_vector(value, *args, **kwargs):
        # Three-value grid vectors are part of LocalizedDesignGrid parsing;
        # anything larger would be a full mask rather than a slab here.
        if np.asanyarray(value).size > 3:
            raise AssertionError("full-grid relationship temporary allocated")
        return original_any(value, *args, **kwargs)

    monkeypatch.setattr(geometry_snapshot_module.np, "any", reject_full_vector)
    assert load_and_verify_local_design_geometry_mask_snapshot(snapshot.path).snapshot.sha256 == snapshot.sha256
