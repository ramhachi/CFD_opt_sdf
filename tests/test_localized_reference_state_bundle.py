from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
import yaml
from typer.testing import CliRunner

import cfd_sdf.cli as cli_module
import cfd_sdf.localized_reference_state_bundle as bundle_module
from cfd_sdf.cli import app
from cfd_sdf.local_design_geometry_snapshot import create_local_design_geometry_mask_snapshot
from cfd_sdf.localized_reference_state_bundle import (
    LOCALIZED_REFERENCE_STATE_FILENAME,
    build_localized_reference_state_bundle,
    localized_reference_state_failure_report_path,
    verify_localized_reference_state_bundle,
)

runner = CliRunner()


def _box(path: Path, center: tuple[float, float, float], extent: tuple[float, float, float]) -> None:
    mesh = trimesh.creation.box(extents=extent)
    mesh.apply_translation(center)
    mesh.export(path)


def _project(tmp_path: Path) -> Path:
    data = yaml.safe_load(Path("examples/g2_openfoam_compile/project.yaml").read_text(encoding="utf-8"))
    geometry = tmp_path / "geometry"; geometry.mkdir()
    _box(geometry / "design.stl", (1.0, 1.0, 1.0), (2.0, 2.0, 2.0))
    _box(geometry / "fixed.stl", (0.25, 0.25, 0.25), (0.2, 0.2, 0.2))
    _box(geometry / "root.stl", (0.25, 0.25, 0.25), (0.2, 0.2, 0.2))
    _box(geometry / "forbidden.stl", (2.3, 2.3, 2.3), (0.1, 0.1, 0.1))
    _box(geometry / "initial.stl", (1.0, 1.0, 1.0), (1.2, 1.2, 1.2))
    data["geometry_regions"] = [
        {"id": "design", "role": "design_domain", "file": "geometry/design.stl"},
        {"id": "fixed", "role": "fixed_solid", "file": "geometry/fixed.stl"},
        {"id": "root", "role": "root", "file": "geometry/root.stl"},
        {"id": "forbidden", "role": "forbidden_region", "file": "geometry/forbidden.stl"},
        {"id": "initial", "role": "initial_design", "file": "geometry/initial.stl"},
    ]
    data["topology_policy"]["root_groups"] = [{"id": "mounts", "region_ids": ["root"]}]
    data["topology_policy"]["minimum_solid_width_m"] = 0.5
    data["topology_policy"]["minimum_void_width_m"] = 0.5
    data["topology_policy"]["minimum_gap_m"] = 0.5
    data["topology_policy"]["erosion_radius_m"] = 0.5
    data["design_grid"] = {
        "kind": "uniform_cartesian", "design_domain_region_id": "design", "voxel_size_m": 0.5,
        "domain_bounds_m": {"lower": [0.0, 0.0, 0.0], "upper": [2.0, 2.0, 2.0]},
        "expected_cell_shape": [4, 4, 4], "expected_cell_count": 64,
        "topology_resolution": {"minimum_solid_width_cells": 1, "minimum_void_width_cells": 1, "minimum_gap_cells": 1, "erosion_radius_cells": 1},
    }
    path = tmp_path / "project.yaml"; path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _bundle(tmp_path: Path) -> tuple[Path, Path]:
    project = _project(tmp_path)
    snapshot = create_local_design_geometry_mask_snapshot(project, output_dir=tmp_path / "snapshot", z_chunk_size=1, containment_chunk_size=8)
    bundle = build_localized_reference_state_bundle(
        project, geometry_snapshot_path=snapshot.snapshot.path, output_dir=tmp_path / "bundle",
        expected_component_count=1, z_slab_size=1,
        disk_free_bytes=lambda _path: 9 * 1024**3, available_memory_bytes=lambda: 9 * 1024**3,
    )
    return project, bundle.path


def test_builds_self_contained_bundle_and_independently_verifies(tmp_path: Path) -> None:
    project, bundle = _bundle(tmp_path)
    verified = verify_localized_reference_state_bundle(bundle, problem=project)
    assert verified.path == bundle
    assert (bundle / "geometry_snapshot" / "masks" / "active_design_mask.npy").is_file()
    assert (bundle / "raw" / "rho_raw.npy").is_file()
    assert (bundle / "states" / "rho_filtered.npy").is_file()
    assert (bundle / "states" / "rho_projected.npy").is_file()
    raw = np.load(bundle / "raw" / "rho_raw.npy", allow_pickle=False)
    assert np.all(raw * 8.0 == np.rint(raw * 8.0))
    ledger = json.loads((bundle / LOCALIZED_REFERENCE_STATE_FILENAME).read_text(encoding="utf-8"))
    state = json.loads((bundle / "localized_design_state_manifest.json").read_text(encoding="utf-8"))
    assert state["states"]["rho"]["relative_path"] == "raw/rho_raw.npy"
    assert ledger["geometry_snapshot_relative_path"] == "geometry_snapshot/local_geometry_masks.json"


@pytest.mark.parametrize("resource", ["disk", "memory"])
def test_refuses_bad_resources_without_publishing(tmp_path: Path, resource: str) -> None:
    project = _project(tmp_path)
    snapshot = create_local_design_geometry_mask_snapshot(project, output_dir=tmp_path / "snapshot", z_chunk_size=1, containment_chunk_size=8)
    with pytest.raises(ValueError, match="8 GiB"):
        build_localized_reference_state_bundle(
            project, geometry_snapshot_path=snapshot.snapshot.path, output_dir=tmp_path / "bundle",
            expected_component_count=1,
            disk_free_bytes=lambda _path: (1 if resource == "disk" else 9) * 1024**3,
            available_memory_bytes=lambda: (1 if resource == "memory" else 9) * 1024**3,
        )
    assert not (tmp_path / "bundle").exists()


def test_refuses_mismatched_snapshot_source_and_cleans_staging(tmp_path: Path) -> None:
    project = _project(tmp_path)
    snapshot = create_local_design_geometry_mask_snapshot(project, output_dir=tmp_path / "snapshot", z_chunk_size=1, containment_chunk_size=8)
    (tmp_path / "geometry" / "initial.stl").write_bytes(b"substituted")
    with pytest.raises(ValueError, match="hash"):
        build_localized_reference_state_bundle(
            project, geometry_snapshot_path=snapshot.snapshot.path, output_dir=tmp_path / "bundle", expected_component_count=1,
            disk_free_bytes=lambda _path: 9 * 1024**3, available_memory_bytes=lambda: 9 * 1024**3,
        )
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".bundle.tmp-*"))


def test_injected_build_failure_closes_staging_and_publishes_only_diagnostic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path)
    snapshot = create_local_design_geometry_mask_snapshot(
        project, output_dir=tmp_path / "snapshot", z_chunk_size=1, containment_chunk_size=8
    )

    def fail_after_active_mask(**_kwargs):
        raise ValueError("injected raw-state failure")

    monkeypatch.setattr(bundle_module, "build_local_initial_design_rho_raw", fail_after_active_mask)
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="injected raw-state failure"):
        build_localized_reference_state_bundle(
            project,
            geometry_snapshot_path=snapshot.snapshot.path,
            output_dir=output,
            expected_component_count=1,
            disk_free_bytes=lambda _path: 9 * 1024**3,
            available_memory_bytes=lambda: 9 * 1024**3,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".bundle.tmp-*"))
    report_path = localized_reference_state_failure_report_path(output)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["kind"] == "localized_reference_state_build_failure"
    assert report["status"] == "build_failed"
    assert report["failed_stage"] == "build_raw_initial_design_rho"
    assert report["exception_type"] == "ValueError"
    assert report["exception_message"] == "injected raw-state failure"
    assert report["staging_cleanup"] == "removed"


@pytest.mark.parametrize("target", ["raw", "filter_config", "manifest"])
def test_verifier_rejects_tampered_artifacts(tmp_path: Path, target: str) -> None:
    project, bundle = _bundle(tmp_path)
    if target == "raw":
        raw_path = bundle / "raw" / "rho_raw.npy"
        raw = np.load(raw_path, mmap_mode="r+"); raw[1] = 0.375; raw.flush(); del raw
    elif target == "filter_config":
        path = bundle / "configs" / "filter_config.json"
        path.write_text(path.read_text(encoding="utf-8").replace("0.004", "0.003"), encoding="utf-8")
    else:
        path = bundle / LOCALIZED_REFERENCE_STATE_FILENAME
        data = json.loads(path.read_text(encoding="utf-8")); data["grid_sha256"] = "0" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_localized_reference_state_bundle(bundle, problem=project)


def test_cli_builds_fixed_contract_bundle_and_prints_verified_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path)
    snapshot = create_local_design_geometry_mask_snapshot(project, output_dir=tmp_path / "snapshot", z_chunk_size=1, containment_chunk_size=8)

    def injected_core(problem_yaml: Path, *, geometry_snapshot_path: Path, output_dir: Path):
        return build_localized_reference_state_bundle(
            problem_yaml, geometry_snapshot_path=geometry_snapshot_path, output_dir=output_dir,
            expected_component_count=1,
            disk_free_bytes=lambda _path: 9 * 1024**3, available_memory_bytes=lambda: 9 * 1024**3,
        )

    monkeypatch.setattr(cli_module, "build_localized_reference_state_bundle", injected_core)
    output = tmp_path / "bundle"
    result = runner.invoke(app, ["build-localized-reference-state", str(project), str(snapshot.snapshot.path), str(output)])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["bundle_path"] == str(output)
    assert summary["ledger_path"] == str(output / LOCALIZED_REFERENCE_STATE_FILENAME)
    assert len(summary["state_manifest_sha256"]) == 64


def test_cli_reports_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_module,
        "build_localized_reference_state_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("insufficient resource guard")),
    )
    result = runner.invoke(app, ["build-localized-reference-state", "project.yaml", "snapshot.json", str(tmp_path / "bundle")])
    assert result.exit_code != 0
    assert "insufficient resource guard" in result.output
