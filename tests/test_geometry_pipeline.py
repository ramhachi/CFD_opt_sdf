"""Geometry-service checks kept from the retired front-wing pipeline tests (SDF build, constraints, VTK export)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cfd_sdf.config import load_project
from cfd_sdf.constraints import check_constraints
from cfd_sdf.export_vtk import export_vti, export_zero_surface
from cfd_sdf.parametric import build_parametric_front_wing, default_parameters, mock_aero
from cfd_sdf.sample_geometry import write_front_wing_demo_geometry
from cfd_sdf.sdf import build_fields
from cfd_sdf.validation import validate_outputs


def test_demo_pipeline_exports_valid_outputs(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path, voxel_size_m=0.06)
    config = load_project(project_yaml)
    bundle = build_fields(config)
    report, derived = check_constraints(config, bundle)
    assert report.ok

    config.resolved_output_dir.mkdir(parents=True, exist_ok=True)
    (config.resolved_output_dir / "report.json").write_text(
        json.dumps(report.to_dict(), indent=2),
        encoding="utf-8",
    )
    export_vti(bundle, config.resolved_output_dir, derived)
    export_zero_surface(bundle, config.resolved_output_dir)

    result = validate_outputs(config, expect_ok=True)
    assert result.ok, result.to_dict()
    assert result.point_count > 0


def test_missing_roots_fail_connectivity(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path, include_roots=False)
    config = load_project(project_yaml)
    bundle = build_fields(config)
    report, _ = check_constraints(config, bundle)
    assert not report.ok
    assert report.nominal_unrooted_components >= 1


def test_forbidden_intersection_fails(tmp_path: Path) -> None:
    project_yaml = _write_project(
        tmp_path,
        forbidden_file="geometry/front_wing_initial.stl",
    )
    config = load_project(project_yaml)
    bundle = build_fields(config)
    report, _ = check_constraints(config, bundle)
    assert not report.ok
    assert report.forbidden_intersection_cells > 0


def test_parametric_front_wing_and_mock_aero() -> None:
    params = default_parameters()
    mesh = build_parametric_front_wing(params)
    aero = mock_aero(params, efficiency_min=3.0)

    assert not mesh.is_empty
    assert aero["drag_coefficient"] > 0
    assert aero["downforce_coefficient"] > 0
    assert "efficiency_constraint" in aero


def _write_project(
    tmp_path: Path,
    *,
    include_roots: bool = True,
    forbidden_file: str = "geometry/forbidden_tire_clearance.stl",
    voxel_size_m: float = 0.10,
    enforce_front_ratio: bool = False,
    include_reference_values: bool = True,
) -> Path:
    write_front_wing_demo_geometry(tmp_path / "geometry")
    roots = [
        {"id": "root_mount_left", "type": "stl", "file": "geometry/root_mount_left.stl"},
        {"id": "root_mount_right", "type": "stl", "file": "geometry/root_mount_right.stl"},
    ] if include_roots else []
    data = {
        "geometry": {
            "fixed_solids": [
                {"id": "vehicle_nose", "file": "geometry/vehicle_nose.stl"},
                {"id": "tire_fl", "file": "geometry/tire_fl.stl"},
                {"id": "tire_fr", "file": "geometry/tire_fr.stl"},
                {"id": "ground", "file": "geometry/ground.stl"},
            ],
            "design_geometry": [
                {"id": "front_wing_initial", "file": "geometry/front_wing_initial.stl"},
            ],
            "design_domains": [
                {"id": "allowed_front_box", "file": "geometry/allowed_front_box.stl"},
            ],
            "forbidden_regions": [
                {"id": "forbidden_tire_clearance", "file": forbidden_file},
            ],
        },
        "roots": roots,
        "grid": {
            "voxel_size_m": voxel_size_m,
            "padding_m": 0.12,
            "band_width_m": 0.20,
            "max_points": 2_000_000,
        },
        "constraints": {
            "min_thickness_mm": 10.0,
            "rule_margin_mm": 5.0,
            "require_eroded_connectivity": True,
            "front_downforce_ratio": {
                "enabled": True,
                "enforce": enforce_front_ratio,
                "x_split_m": 0.0,
                "min": 0.4,
                "max": 0.6,
            },
        },
        "objective": {
            "type": "maximize_downforce_with_efficiency_constraint",
            "efficiency_min": 3.0,
        },
        "operating_point": {
            "velocity_mps": 11.0,
            "density": 1.229,
            "viscosity": 1.73e-5,
        },
        "output_dir": "runs/front_wing_demo",
    }
    if include_reference_values:
        data["reference_values"] = {"area_m2": 0.35, "length_m": 1.6}
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return project_yaml
