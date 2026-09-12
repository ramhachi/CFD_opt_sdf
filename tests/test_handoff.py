from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv
import trimesh
from typer.testing import CliRunner

from cfd_sdf.cli import app
from cfd_sdf.fixed_grid_contract import CartesianCellGrid, _write_cell_vti
from cfd_sdf.handoff import (
    DISCRETENESS_MAX_MEAN_ND,
    HANDOFF_KIND,
    SDF_KIND,
    SDF_SIGN_CONVENTION,
    SURFACE_CLEAN_TOLERANCE_FRACTION,
    _discreteness_report,
    _surface_quality_metrics,
    build_density_to_sdf_handoff,
)


runner = CliRunner()


def test_cell_density_handoff_writes_hashed_stl_sdf_and_reports_provenance(
    tmp_path: Path,
) -> None:
    state_path = _write_state(tmp_path / "candidate", cell_shape=(6, 6, 6))

    artifacts = build_density_to_sdf_handoff(
        state_path,
        output_dir=tmp_path / "handoff",
        expected_topology_state_sha256=_sha256(state_path),
        expected_density_vti_sha256=_sha256(state_path.parent / "density.vti"),
    )

    assert artifacts.ok is True
    assert artifacts.surface_stl.exists()
    assert artifacts.sdf_vti.exists()
    assert artifacts.bundled_topology_state_json.read_bytes() == state_path.read_bytes()
    assert artifacts.bundled_density_vti.read_bytes() == (
        state_path.parent / "density.vti"
    ).read_bytes()
    assert artifacts.revoxelized_density_vti.exists()
    assert artifacts.geometry_binding_json.exists()
    assert artifacts.fidelity_report_json.exists()
    assert artifacts.manifest_json.exists()

    manifest = json.loads(artifacts.manifest_json.read_text(encoding="utf-8"))
    assert manifest["kind"] == HANDOFF_KIND
    assert manifest["status"] == "diagnostic_only"
    assert manifest["ready_for_stage_s"] is False
    assert manifest["qualification"] == "geometry_handoff_capability_only"
    assert manifest["inputs"]["topology_state_json"]["sha256"] == _sha256(state_path)
    assert manifest["inputs"]["density_vti"]["sha256"] == _sha256(
        state_path.parent / "density.vti"
    )
    assert manifest["rho"]["variant"] == "rho"
    assert manifest["rho"]["selection_source"] == "topology_state.json:density_array"
    assert manifest["rho"]["location"] == "cell"
    assert manifest["rho"]["iso_value"] == 0.5
    assert manifest["rho"]["iso_value_source"] == "default"
    assert manifest["rho"]["surface_density_policy"] == "rho_with_fixed_solid_overlay"
    assert manifest["grid_transform"]["kind"] == "identity"
    assert manifest["grid_transform"]["source_grid"]["cell_order"] == "vtk-x-fastest"
    assert manifest["grid_transform"]["cell_to_point"]["method"] == (
        "vtk_cell_data_to_point_data"
    )
    assert manifest["sdf"]["sign_convention"] == SDF_SIGN_CONVENTION
    assert manifest["artifacts"]["surface_stl"]["sha256"] == _sha256(
        artifacts.surface_stl
    )
    assert manifest["artifacts"]["sdf_vti"]["sha256"] == _sha256(artifacts.sdf_vti)
    assert manifest["artifacts"]["revoxelized_density_vti"]["sha256"] == _sha256(
        artifacts.revoxelized_density_vti
    )
    assert manifest["artifacts"]["geometry_binding"]["sha256"] == _sha256(
        artifacts.geometry_binding_json
    )

    sdf = pv.read(artifacts.sdf_vti)
    assert sdf.dimensions == (7, 7, 7)
    assert sdf.point_data["sdf"].shape == (7 * 7 * 7,)
    assert np.isfinite(sdf.point_data["sdf"]).all()
    assert str(np.asarray(sdf.field_data["kind"]).ravel()[0]) == SDF_KIND
    assert str(np.asarray(sdf.field_data["sdf_sign_convention"]).ravel()[0]) == (
        SDF_SIGN_CONVENTION
    )

    report = json.loads(artifacts.fidelity_report_json.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["ready_for_stage_s"] is False
    assert report["checks"]["cell_data_contract"] is True
    assert report["checks"]["source_mask_validation"] is True
    assert report["checks"]["source_component_validation"] is True
    assert report["checks"]["revoxelized_mask_validation"] is True
    assert report["checks"]["revoxelized_component_validation"] is True
    assert (
        report["source_material_checks"]["components"]["root_connectivity"]["status"]
        == "pass"
    )
    assert (
        report["revoxelized_geometry_checks"]["components"]["root_connectivity"]["status"]
        == "pass"
    )
    assert report["surface"]["watertight"] is True
    assert report["sdf"]["sign_convention"] == SDF_SIGN_CONVENTION
    assert report["volume"]["revoxelized_cell_volume_m3"] > 0.0


def test_handoff_records_explicit_rho_variant_and_iso_value(tmp_path: Path) -> None:
    state_path = _write_state(tmp_path / "candidate", cell_shape=(6, 6, 6))

    artifacts = build_density_to_sdf_handoff(
        state_path,
        output_dir=tmp_path / "handoff",
        rho_variant="rho_filtered",
        iso_value=0.25,
    )

    assert artifacts.manifest["rho"]["variant"] == "rho_filtered"
    assert artifacts.manifest["rho"]["selection_source"] == "function_argument"
    assert artifacts.manifest["rho"]["iso_value"] == 0.25
    assert artifacts.manifest["rho"]["iso_value_source"] == "function_argument"


def test_handoff_reports_revoxelized_geometry_loss_separately(tmp_path: Path) -> None:
    # A 2x2x2 solid box (the smallest fully-enclosed block) interpolates to a single
    # near-threshold point under cell-to-point averaging; its raw marching-cubes surface is a
    # pure numerical artifact (triangle areas down to ~1e-12) that the surface-cleaning step in
    # build_density_to_sdf_handoff now correctly discards outright (see
    # test_surface_cleaning_rejects_a_fully_degenerate_iso_surface). A 4x4x4 box still shrinks
    # sharply under interpolation (only its innermost 2x2x2 sub-lattice of points reaches the
    # solid threshold), demonstrating the same source-vs-revoxelized geometry loss, but the
    # shrunk surface is a genuine (if small) cube rather than a degenerate point, so it survives
    # cleaning and this test still exercises the intended assertions.
    state_path = _write_state(
        tmp_path / "candidate",
        cell_shape=(6, 6, 6),
        solid_boxes=(((1, 4), (1, 4), (1, 4)),),
        root_cell=(1, 1, 1),
    )
    density_path = state_path.parent / "density.vti"
    density_grid = pv.read(density_path)
    for name in ("rho", "rho_filtered", "rho_projected"):
        values = np.asarray(density_grid.cell_data[name], dtype=np.float32).copy()
        values[values > 0.0] = np.float32(0.5000006)
        density_grid.cell_data[name] = values
    density_grid.save(density_path)

    artifacts = build_density_to_sdf_handoff(
        state_path,
        output_dir=tmp_path / "handoff",
    )
    report = artifacts.fidelity_report

    assert report["checks"]["source_component_validation"] is True
    assert report["checks"]["revoxelized_component_validation"] is False
    assert report["volume"]["revoxelized_cell_volume_m3"] < report["volume"]["cell_threshold_volume_m3"]
    assert (
        report["source_material_checks"]["components"]["root_connectivity"]["status"]
        == "pass"
    )
    assert (
        report["revoxelized_geometry_checks"]["components"]["root_connectivity"]["status"]
        == "fail"
    )
    assert "revoxelized_component_validation_failed" in report["qualification_reasons"]


def test_surface_cleaning_rejects_a_fully_degenerate_iso_surface(tmp_path: Path) -> None:
    # A 2x2x2 solid box is the smallest fully-enclosed block: under cell-to-point averaging only
    # its single interior corner clears the 0.5 threshold, so the raw marching-cubes surface is a
    # near-zero-size numerical artifact (triangle areas ~1e-12) rather than a real feature.
    # Cleaning must reject this outright instead of silently handing Stage S a fake sliver body.
    state_path = _write_state(
        tmp_path / "candidate",
        cell_shape=(6, 6, 6),
        solid_boxes=(((2, 3), (2, 3), (2, 3)),),
        root_cell=(2, 2, 2),
    )
    density_path = state_path.parent / "density.vti"
    density_grid = pv.read(density_path)
    for name in ("rho", "rho_filtered", "rho_projected"):
        values = np.asarray(density_grid.cell_data[name], dtype=np.float32).copy()
        values[values > 0.0] = np.float32(0.5000006)
        density_grid.cell_data[name] = values
    density_grid.save(density_path)

    with pytest.raises(ValueError, match="Surface cleaning removed the entire iso-surface"):
        build_density_to_sdf_handoff(state_path, output_dir=tmp_path / "handoff")


def test_handoff_reports_surface_quality_before_and_after_cleaning(tmp_path: Path) -> None:
    # Same near-threshold perturbation as the geometry-loss test above, on a box big enough
    # (4x4x4) that the shrunk surface is a real cube rather than a degenerate point: this is the
    # sliver-producing scenario the cleaning step in build_density_to_sdf_handoff targets.
    state_path = _write_state(
        tmp_path / "candidate",
        cell_shape=(6, 6, 6),
        solid_boxes=(((1, 4), (1, 4), (1, 4)),),
        root_cell=(1, 1, 1),
    )
    density_path = state_path.parent / "density.vti"
    density_grid = pv.read(density_path)
    for name in ("rho", "rho_filtered", "rho_projected"):
        values = np.asarray(density_grid.cell_data[name], dtype=np.float32).copy()
        values[values > 0.0] = np.float32(0.5000006)
        density_grid.cell_data[name] = values
    density_grid.save(density_path)

    artifacts = build_density_to_sdf_handoff(state_path, output_dir=tmp_path / "handoff")
    quality = artifacts.fidelity_report["surface_quality"]

    assert quality["clean_tolerance_m"] == pytest.approx(SURFACE_CLEAN_TOLERANCE_FRACTION * 1.0)
    assert quality["before_cleaning"]["count_aspect_ratio_above_100"] > 0
    assert quality["after_cleaning"]["count_aspect_ratio_above_100"] == 0
    assert quality["after_cleaning"]["max_aspect_ratio"] < quality["before_cleaning"]["max_aspect_ratio"]
    assert quality["faces_removed_by_cleaning"] > 0
    # The written STL is the cleaned one: no leftover slivers make it into the artifact.
    mesh = trimesh.load_mesh(artifacts.surface_stl, process=False)
    assert len(mesh.faces) == quality["after_cleaning"]["face_count"]


def test_surface_quality_metrics_detects_a_sliver_triangle() -> None:
    # A near-degenerate triangle (a hair's-width from collinear) must register a large aspect
    # ratio; an equilateral triangle must register close to 1. Isolated unit test of the metric
    # used to size the cleaning tolerance and to report before/after fidelity.
    sliver = pv.PolyData(
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 1e-6, 0.0]]),
        faces=np.array([3, 0, 1, 2]),
    )
    equilateral = pv.PolyData(
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 3.0**0.5 / 2.0, 0.0]]),
        faces=np.array([3, 0, 1, 2]),
    )

    sliver_metrics = _surface_quality_metrics(sliver)
    equilateral_metrics = _surface_quality_metrics(equilateral)

    assert sliver_metrics["max_aspect_ratio"] > 1000.0
    assert sliver_metrics["count_aspect_ratio_above_100"] == 1
    # longest-edge / (2 * inradius) is sqrt(3) =~ 1.732 for an equilateral triangle, its minimum
    # over all triangle shapes; a sliver's ratio is unbounded above.
    assert equilateral_metrics["max_aspect_ratio"] == pytest.approx(3.0**0.5, abs=1e-6)
    assert equilateral_metrics["count_aspect_ratio_above_50"] == 0


def test_discreteness_measure_arithmetic() -> None:
    # Hand-computed: mean(4*rho*(1-rho)) over the active cells only. Of the
    # active cells, rho=0 and rho=1 each contribute 0; rho=0.5 contributes
    # 4*0.5*0.5=1.0. The fourth cell (rho=0.9) is masked inactive and must
    # not affect the mean. Mean over the 3 active cells = 1.0/3.
    density = np.array([0.0, 1.0, 0.5, 0.9], dtype=np.float64)
    masks = {"active_design_mask": np.array([1, 1, 1, 0], dtype=np.uint8)}

    result = _discreteness_report(density, masks)

    assert result["scope"] == "active_design_mask"
    assert result["cell_count"] == 3
    assert result["mean_nd"] == pytest.approx(1.0 / 3.0)
    assert result["max_rho"] == pytest.approx(1.0)
    assert result["count_rho_above_0_9"] == 1
    assert result["count_rho_below_0_1"] == 1
    assert result["count_rho_grey_band"] == 1
    assert result["status"] == "fail"


def test_handoff_passes_discreteness_gate_for_near_binary_field(tmp_path: Path) -> None:
    # The shared fixture writes a purely 0/1 density field, so mean_nd is
    # exactly zero and must clear the gate.
    state_path = _write_state(tmp_path / "candidate", cell_shape=(6, 6, 6))

    artifacts = build_density_to_sdf_handoff(state_path, output_dir=tmp_path / "handoff")

    report = artifacts.fidelity_report
    assert report["discreteness"]["mean_nd"] == 0.0
    assert report["discreteness"]["status"] == "pass"
    assert report["discreteness"]["max_mean_nd_allowed"] == DISCRETENESS_MAX_MEAN_ND
    assert "density_field_not_sufficiently_discrete" not in report["qualification_reasons"]
    manifest = json.loads(artifacts.manifest_json.read_text(encoding="utf-8"))
    assert "density_field_not_sufficiently_discrete" not in manifest["qualification_reasons"]


def test_handoff_flags_grey_density_field_as_not_discrete(tmp_path: Path) -> None:
    state_path = _write_state(tmp_path / "candidate", cell_shape=(6, 6, 6))
    density_path = state_path.parent / "density.vti"
    density_grid = pv.read(density_path)
    for name in ("rho", "rho_filtered", "rho_projected"):
        values = np.asarray(density_grid.cell_data[name], dtype=np.float32).copy()
        # The fixture's solid box sits at rho=1; smear it to a mid-grey value
        # well short of binary, like the two measured real candidates.
        values[values > 0.0] = np.float32(0.6)
        density_grid.cell_data[name] = values
    density_grid.save(density_path)

    artifacts = build_density_to_sdf_handoff(state_path, output_dir=tmp_path / "handoff")

    report = artifacts.fidelity_report
    assert report["discreteness"]["mean_nd"] > DISCRETENESS_MAX_MEAN_ND
    assert report["discreteness"]["mean_status"] == "fail"
    assert report["discreteness"]["max_status"] == "fail"
    assert report["discreteness"]["status"] == "fail"
    assert report["discreteness"]["count_rho_above_0_9"] == 0
    assert "density_field_not_sufficiently_discrete" in report["qualification_reasons"]
    assert report["ready_for_stage_s"] is False
    manifest = json.loads(artifacts.manifest_json.read_text(encoding="utf-8"))
    assert "density_field_not_sufficiently_discrete" in manifest["qualification_reasons"]
    assert manifest["discreteness"]["status"] == "fail"


def test_handoff_flags_small_grey_body_that_fools_the_mean_threshold(
    tmp_path: Path,
) -> None:
    # A small, fully-grey body diluted by a large void can drive mean_nd
    # below DISCRETENESS_MAX_MEAN_ND on its own -- averaging against void
    # cells hides that the object itself never commits to solid. This is the
    # loophole DISCRETENESS_MIN_MAX_RHO exists to close: the object's 8 cells
    # sit at rho=0.6 among 1000 active cells, so mean_nd = 8*4*0.6*0.4/1000
    # = 0.00768, comfortably under the mean threshold, yet every one of those
    # cells is far from solid.
    state_path = _write_state(
        tmp_path / "candidate",
        cell_shape=(10, 10, 10),
        solid_boxes=(((1, 2), (1, 2), (1, 2)),),
        root_cell=(1, 1, 1),
    )
    density_path = state_path.parent / "density.vti"
    density_grid = pv.read(density_path)
    for name in ("rho", "rho_filtered", "rho_projected"):
        values = np.asarray(density_grid.cell_data[name], dtype=np.float32).copy()
        values[values > 0.0] = np.float32(0.6)
        density_grid.cell_data[name] = values
    density_grid.save(density_path)

    artifacts = build_density_to_sdf_handoff(state_path, output_dir=tmp_path / "handoff")

    report = artifacts.fidelity_report
    assert report["discreteness"]["mean_nd"] <= DISCRETENESS_MAX_MEAN_ND
    assert report["discreteness"]["mean_status"] == "pass"
    assert report["discreteness"]["max_rho"] == pytest.approx(0.6)
    assert report["discreteness"]["max_status"] == "fail"
    assert report["discreteness"]["status"] == "fail"
    assert "density_field_not_sufficiently_discrete" in report["qualification_reasons"]
    assert report["ready_for_stage_s"] is False


def test_handoff_requires_cell_data_and_rejects_invalid_mask(tmp_path: Path) -> None:
    point_only = tmp_path / "point_only"
    point_only.mkdir()
    grid = pv.ImageData(dimensions=(4, 4, 4), spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0))
    grid.point_data["rho"] = np.ones(grid.n_points, dtype=np.float32)
    grid.field_data["schema_version"] = np.array([1], dtype=np.int32)
    grid.field_data["kind"] = np.array(["fixed_grid_density"])
    grid.field_data["cell_order"] = np.array(["vtk-x-fastest"])
    grid.save(point_only / "density.vti")
    point_state = _state_dict(
        CartesianCellGrid((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (3, 3, 3)),
        "density.vti",
    )
    (point_only / "topology_state.json").write_text(
        json.dumps(point_state), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="missing cell-data array"):
        build_density_to_sdf_handoff(point_only / "topology_state.json")

    invalid = _write_state(tmp_path / "invalid_mask", cell_shape=(6, 6, 6))
    density_path = invalid.parent / "density.vti"
    density = pv.read(density_path)
    forbidden = np.asarray(density.cell_data["forbidden_mask"], dtype=np.uint8).copy()
    forbidden[_cell_index((2, 2, 2), (6, 6, 6))] = 1
    density.cell_data["forbidden_mask"] = forbidden
    density.save(density_path)
    with pytest.raises(ValueError, match="mask validation failed: forbidden_mask"):
        build_density_to_sdf_handoff(invalid, output_dir=tmp_path / "invalid_out")
    assert not (tmp_path / "invalid_out").exists()


def test_handoff_rejects_unrooted_component_and_hash_mismatch(tmp_path: Path) -> None:
    state_path = _write_state(
        tmp_path / "disconnected",
        cell_shape=(8, 4, 4),
        solid_boxes=(((1, 2), (1, 2), (1, 2)), ((5, 6), (1, 2), (1, 2))),
        root_cell=(1, 1, 1),
    )
    with pytest.raises(ValueError, match="connectivity validation failed: root_connectivity"):
        build_density_to_sdf_handoff(state_path, output_dir=tmp_path / "disconnected_out")
    assert not (tmp_path / "disconnected_out").exists()

    valid = _write_state(tmp_path / "hash", cell_shape=(6, 6, 6))
    with pytest.raises(ValueError, match="expected_topology_state_sha256 does not match"):
        build_density_to_sdf_handoff(valid, expected_topology_state_sha256="0" * 64)


def test_handoff_cli_writes_the_same_provenance_bound_artifacts(tmp_path: Path) -> None:
    state_path = _write_state(tmp_path / "candidate", cell_shape=(6, 6, 6))
    output_dir = tmp_path / "handoff"

    result = runner.invoke(
        app,
        [
            "build-density-sdf-handoff",
            str(state_path),
            "--output-dir",
            str(output_dir),
            "--expected-topology-state-sha256",
            _sha256(state_path),
            "--expected-density-vti-sha256",
            _sha256(state_path.parent / "density.vti"),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads((output_dir / "handoff_manifest.json").read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert manifest["qualification"] == "geometry_handoff_capability_only"
    assert (output_dir / "iso_surface.stl").exists()
    assert (output_dir / "signed_distance.vti").exists()
    assert (output_dir / "revoxelized_density.vti").exists()
    assert (output_dir / "geometry_binding.json").exists()

    repeated = runner.invoke(
        app,
        [
            "build-density-sdf-handoff",
            str(state_path),
            "--output-dir",
            str(output_dir),
        ],
    )
    assert repeated.exit_code != 0
    assert "output is immutable" in repeated.output


def _write_state(
    directory: Path,
    *,
    cell_shape: tuple[int, int, int],
    solid_boxes: tuple[
        tuple[tuple[int, int], tuple[int, int], tuple[int, int]], ...
    ] = (((1, 4), (1, 4), (1, 4)),),
    root_cell: tuple[int, int, int] | None = (1, 3, 3),
) -> Path:
    directory.mkdir(parents=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0),
        spacing=(1.0, 1.0, 1.0),
        cell_shape=cell_shape,
    )
    count = grid.cell_count
    density = np.zeros(count, dtype=np.float32)
    for box in solid_boxes:
        for x in range(box[0][0], box[0][1] + 1):
            for y in range(box[1][0], box[1][1] + 1):
                for z in range(box[2][0], box[2][1] + 1):
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
    state = _state_dict(grid, "density.vti")
    (directory / "topology_state.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )
    return directory / "topology_state.json"


def _state_dict(grid: CartesianCellGrid, density_name: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "density_vti": density_name,
        "density_array": "rho",
        "array_metadata": {"rho": {"location": "cell", "units": "1"}},
    }


def _cell_index(
    cell: tuple[int, int, int], shape: tuple[int, int, int]
) -> int:
    return int(np.ravel_multi_index(cell, shape, order="F"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
