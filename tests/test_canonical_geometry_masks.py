from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
import trimesh
import yaml

from cfd_sdf.canonical_geometry_masks import (
    CANONICAL_GEOMETRY_MASK_MANIFEST_KIND,
    build_canonical_geometry_mask_snapshot,
    verify_canonical_geometry_mask_manifest,
)
from cfd_sdf.canonical_grid_snapshot import load_and_verify_canonical_grid_snapshot
from cfd_sdf.problem_spec import load_problem_spec


def _base_data() -> dict:
    return yaml.safe_load(Path("examples/g2_openfoam_compile/project.yaml").read_text(encoding="utf-8"))


def _write_box(path: Path, *, center: tuple[float, float, float], extents: tuple[float, float, float]) -> None:
    transform = trimesh.transformations.translation_matrix(center)
    trimesh.creation.box(extents=extents, transform=transform).export(path)


def _write_problem(
    tmp_path: Path,
    *,
    root_center: tuple[float, float, float] = (0.25, 0.25, 0.25),
    fixed_center: tuple[float, float, float] = (0.25, 0.25, 0.25),
    forbidden_center: tuple[float, float, float] = (-0.25, -0.25, -0.25),
    design_extents: tuple[float, float, float] = (3.0, 3.0, 3.0),
) -> Path:
    geometry = tmp_path / "geometry"
    geometry.mkdir(parents=True)
    _write_box(geometry / "vehicle.stl", center=fixed_center, extents=(0.3, 0.3, 0.3))
    _write_box(geometry / "initial_surface.stl", center=(0.0, 0.0, 0.0), extents=(0.3, 0.3, 0.3))
    _write_box(geometry / "design_domain.stl", center=(0.0, 0.0, 0.0), extents=design_extents)
    _write_box(geometry / "keepout.stl", center=forbidden_center, extents=(0.3, 0.3, 0.3))
    _write_box(geometry / "mount.stl", center=root_center, extents=(0.3, 0.3, 0.3))
    data = _base_data()
    # Synthetic-mask fixtures deliberately do not opt into the production
    # local-design-grid contract; their box geometry is intentionally tiny and
    # unrelated to the authoritative front-wing design domain.
    data.pop("design_grid", None)
    data["grid"] = {
        "kind": "uniform_cartesian",
        "voxel_size_m": 0.5,
        "padding_m": 0.0,
        "domain_bounds_m": {"lower": [-1.0, -1.0, -1.0], "upper": [1.0, 1.0, 1.0]},
    }
    # Keep synthetic-mask tests independent of the production benchmark's
    # intentionally richer multi-part geometry contract.
    data["geometry_regions"] = [
        {"id": "vehicle", "role": "fixed_solid", "file": "geometry/vehicle.stl"},
        {"id": "initial_surface", "role": "initial_design", "file": "geometry/initial_surface.stl"},
        {"id": "design_domain", "role": "design_domain", "file": "geometry/design_domain.stl"},
        {"id": "keepout", "role": "forbidden_region", "file": "geometry/keepout.stl"},
        {"id": "mount", "role": "root", "file": "geometry/mount.stl"},
    ]
    data["topology_policy"] = deepcopy(data["topology_policy"])
    data["topology_policy"]["root_groups"] = [{"id": "mounts", "region_ids": ["mount"]}]
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _write_coarsened_g2_problem(tmp_path: Path) -> Path:
    """Write a CI-sized copy of the real G2 geometry contract.

    The production G2 grid has 1,170,000 cells, which is appropriate for a
    benchmark artifact but unnecessarily expensive for this contract test.
    Geometry paths remain relative so the test also exercises the portable
    source-path resolution used by the real project file.
    """

    source_path = Path("examples/g2_openfoam_compile/project.yaml").resolve()
    data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    data["grid"] = deepcopy(data["grid"])
    data["grid"]["voxel_size_m"] = 0.1
    for region in data["geometry_regions"]:
        asset_path = (source_path.parent / region["file"]).resolve()
        region["file"] = Path(os.path.relpath(asset_path, tmp_path)).as_posix()
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_builds_role_masks_snapshot_and_geometry_provenance(tmp_path: Path) -> None:
    problem_yaml = _write_problem(tmp_path)
    spec = load_problem_spec(problem_yaml)
    artifacts = build_canonical_geometry_mask_snapshot(spec, output_dir=tmp_path / "output", chunk_size=11)

    verified = load_and_verify_canonical_grid_snapshot(artifacts.snapshot_path, spec)
    assert artifacts.grid_cell_count == 64
    assert artifacts.mask_true_counts == {
        "active_design_mask": 62,
        "forbidden_mask": 1,
        "fixed_solid_mask": 1,
        "root_mask": 1,
    }
    assert int(verified.masks["active_design_mask"].sum()) == 62
    assert int(verified.masks["forbidden_mask"].sum()) == 1
    assert int(verified.masks["fixed_solid_mask"].sum()) == 1
    assert np.all(verified.masks["root_mask"] <= verified.masks["fixed_solid_mask"])

    manifest = json.loads(artifacts.geometry_manifest_path.read_text(encoding="utf-8"))
    assert manifest["kind"] == CANONICAL_GEOMETRY_MASK_MANIFEST_KIND
    assert len(manifest["geometry_sources"]) == 5
    assert manifest["masks"]["active_design_mask"]["source_geometry_ids"] == [
        "design_domain",
        "keepout",
        "vehicle",
    ]
    vehicle = tmp_path / "geometry" / "vehicle.stl"
    assert manifest["geometry_sources"]["vehicle"]["sha256"] == hashlib.sha256(
        vehicle.read_bytes()
    ).hexdigest()
    assert manifest["canonical_grid_snapshot"]["sha256"] == hashlib.sha256(
        artifacts.snapshot_path.read_bytes()
    ).hexdigest()
    verified_manifest = verify_canonical_geometry_mask_manifest(
        artifacts.geometry_manifest_path,
        spec,
    )
    assert verified_manifest.mask_true_counts == artifacts.mask_true_counts

    vehicle.write_bytes(vehicle.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="geometry source mismatch: vehicle"):
        verify_canonical_geometry_mask_manifest(artifacts.geometry_manifest_path, spec)


def test_missing_or_nonwatertight_geometry_is_rejected(tmp_path: Path) -> None:
    missing_yaml = _write_problem(tmp_path / "missing")
    (tmp_path / "missing" / "geometry" / "design_domain.stl").unlink()
    with pytest.raises(ValueError, match="Geometry STL is missing"):
        build_canonical_geometry_mask_snapshot(missing_yaml, output_dir=tmp_path / "missing_out")

    invalid_yaml = _write_problem(tmp_path / "nonwatertight")
    mesh = trimesh.Trimesh(
        vertices=np.array(((0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.1, 0.0))),
        faces=np.array(((0, 1, 2),)),
        process=False,
    )
    mesh.export(tmp_path / "nonwatertight" / "geometry" / "design_domain.stl")
    with pytest.raises(ValueError, match="must be watertight"):
        build_canonical_geometry_mask_snapshot(invalid_yaml, output_dir=tmp_path / "nonwatertight_out")


def test_surface_centres_are_rejected(tmp_path: Path) -> None:
    ambiguous_yaml = _write_problem(
        tmp_path / "ambiguous",
        design_extents=(1.5, 1.5, 1.5),
    )
    with pytest.raises(ValueError, match="Containment is ambiguous"):
        build_canonical_geometry_mask_snapshot(ambiguous_yaml, output_dir=tmp_path / "ambiguous_out")


def test_fixed_roots_take_precedence_inside_forbidden_envelope(tmp_path: Path) -> None:
    overlap_yaml = _write_problem(
        tmp_path / "overlap",
        forbidden_center=(0.25, 0.25, 0.25),
    )
    artifacts = build_canonical_geometry_mask_snapshot(
        overlap_yaml,
        output_dir=tmp_path / "overlap_out",
    )
    snapshot = load_and_verify_canonical_grid_snapshot(artifacts.snapshot_path, load_problem_spec(overlap_yaml))
    assert int(snapshot.masks["fixed_solid_mask"].sum()) == 1
    assert int(snapshot.masks["root_mask"].sum()) == 1
    assert int(snapshot.masks["forbidden_mask"].sum()) == 0
    assert np.all(snapshot.masks["root_mask"] <= snapshot.masks["fixed_solid_mask"])
    assert not np.any(snapshot.masks["fixed_solid_mask"] & snapshot.masks["forbidden_mask"])


def test_g2_front_wing_geometry_contract_builds_coarsened_masks(tmp_path: Path) -> None:
    """The real G2 contract consumes the authoritative front-wing STL assets."""

    source_path = Path("examples/g2_openfoam_compile/project.yaml").resolve()
    source_data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    front_wing_geometry = Path("examples/front_wing/geometry").resolve()
    regions = {region["id"]: region for region in source_data["geometry_regions"]}

    assert set(regions) == {
        "vehicle_nose",
        "ground",
        "front_wing_initial",
        "allowed_front_box",
        "tire_clearance",
        "root_mount_left_fixed",
        "root_mount_right_fixed",
        "root_mount_left",
        "root_mount_right",
    }
    assert regions["tire_clearance"]["role"] == "forbidden_region"
    assert regions["tire_clearance"]["file"] == "../front_wing/geometry/forbidden_tire_clearance.stl"
    assert {region_id for region_id, region in regions.items() if region["role"] == "root"} == {
        "root_mount_left",
        "root_mount_right",
    }
    assert {region_id for region_id, region in regions.items() if region["role"] == "fixed_solid"} == {
        "vehicle_nose",
        "ground",
        "root_mount_left_fixed",
        "root_mount_right_fixed",
    }
    assert source_data["topology_policy"]["root_groups"] == [
        {"id": "mounts", "region_ids": ["root_mount_left", "root_mount_right"]}
    ]
    for region in regions.values():
        asset_path = (source_path.parent / region["file"]).resolve()
        assert asset_path.parent == front_wing_geometry
        assert asset_path.is_file()

    problem_yaml = _write_coarsened_g2_problem(tmp_path)
    spec = load_problem_spec(problem_yaml)
    artifacts = build_canonical_geometry_mask_snapshot(
        spec,
        output_dir=tmp_path / "output",
        chunk_size=101,
    )
    snapshot = load_and_verify_canonical_grid_snapshot(artifacts.snapshot_path, spec)
    fixed = snapshot.masks["fixed_solid_mask"]
    root = snapshot.masks["root_mask"]
    forbidden = snapshot.masks["forbidden_mask"]
    active = snapshot.masks["active_design_mask"]
    assert int(active.sum()) > 0
    assert int(fixed.sum()) > 0
    assert int(root.sum()) > 0
    assert int(forbidden.sum()) > 0
    assert np.all(root <= fixed)
    assert not np.any(fixed & forbidden)

    manifest = json.loads(artifacts.geometry_manifest_path.read_text(encoding="utf-8"))
    assert manifest["masks"]["forbidden_mask"]["source_geometry_ids"] == ["tire_clearance"]
    assert manifest["masks"]["root_mask"]["source_geometry_ids"] == [
        "root_mount_left",
        "root_mount_right",
    ]
    assert manifest["masks"]["fixed_solid_mask"]["source_geometry_ids"] == [
        "ground",
        "root_mount_left_fixed",
        "root_mount_right_fixed",
        "vehicle_nose",
    ]
    verified = verify_canonical_geometry_mask_manifest(artifacts.geometry_manifest_path, spec)
    assert verified.mask_true_counts == artifacts.mask_true_counts



def test_root_outside_fixed_and_empty_active_are_rejected(tmp_path: Path) -> None:
    root_yaml = _write_problem(
        tmp_path / "root_outside",
        root_center=(0.75, 0.75, 0.75),
    )
    with pytest.raises(ValueError, match="root_mask must be contained"):
        build_canonical_geometry_mask_snapshot(root_yaml, output_dir=tmp_path / "root_outside_out")

    empty_yaml = _write_problem(tmp_path / "empty")
    data = yaml.safe_load(empty_yaml.read_text(encoding="utf-8"))
    data["geometry_regions"] = deepcopy(data["geometry_regions"])
    data["geometry_regions"][2]["file"] = "geometry/vehicle.stl"
    empty_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="active_design_mask is empty"):
        build_canonical_geometry_mask_snapshot(empty_yaml, output_dir=tmp_path / "empty_out")
