from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
import yaml

from cfd_sdf.geometry_preflight import (
    assess_geometry_preflight,
)


def _problem_data(*, feature_policy: dict[str, float] | None = None) -> dict:
    topology_policy = {
        "root_groups": [],
        "solid_connectivity": {
            "mode": "disabled",
            "required_root_group_ids": [],
            "max_components": None,
            "evaluate_eroded": False,
        },
        "void_connectivity": {
            "mode": "disabled",
            "required_root_group_ids": [],
            "max_components": None,
            "evaluate_eroded": False,
        },
    }
    if feature_policy:
        topology_policy.update(feature_policy)
    return {
        "schema_version": 2,
        "problem_id": "geometry_preflight_fixture",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
        },
        "grid": {
            "kind": "uniform_cartesian",
            "voxel_size_m": 0.04,
            "padding_m": 0.0,
            "domain_bounds_m": {
                "lower": [-0.4, -0.4, -0.4],
                "upper": [0.4, 0.4, 0.4],
            },
        },
        "reference_values": None,
        "geometry_regions": [
            {"id": "box", "role": "design_domain", "file": "geometry/box.stl"},
        ],
        "flow_cases": [
            {
                "id": "straight",
                "freestream_velocity_mps": [10.0, 0.0, 0.0],
                "fluid": {
                    "model": "incompressible_newtonian",
                    "density_kg_m3": 1.225,
                    "dynamic_viscosity_pa_s": 1.8e-5,
                },
                "turbulence": None,
                "boundary_conditions": None,
                "motion_profiles": {},
            }
        ],
        "responses": [
            {
                "id": "force_x",
                "kind": "force",
                "flow_case_id": "straight",
                "direction": [1.0, 0.0, 0.0],
            }
        ],
        "objectives": [
            {
                "id": "force_objective",
                "sense": "minimize",
                "terms": [
                    {
                        "coefficient": 1.0,
                        "flow_case_id": "straight",
                        "response_id": "force_x",
                    }
                ],
            }
        ],
        "constraints": [],
        "topology_policy": topology_policy,
    }


def _write_problem(
    tmp_path: Path,
    *,
    extents: tuple[float, float, float] = (0.24, 0.24, 0.24),
    feature_policy: dict[str, float] | None = None,
) -> Path:
    geometry = tmp_path / "geometry"
    geometry.mkdir(parents=True)
    trimesh.creation.box(extents=extents).export(geometry / "box.stl")
    path = tmp_path / "problem.yaml"
    path.write_text(
        yaml.safe_dump(_problem_data(feature_policy=feature_policy), sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_watertight_box_passes_supported_subset_and_binds_hashes(tmp_path: Path) -> None:
    problem = _write_problem(
        tmp_path,
        feature_policy={
            "minimum_solid_width_m": 0.12,
            "minimum_void_width_m": 0.16,
            "minimum_gap_m": 0.12,
            "erosion_radius_m": 0.04,
        },
    )

    report = assess_geometry_preflight(problem)

    assert report["status"] == "pass"
    assert report["qualification"]["status"] == "not_evaluated"
    assert report["checks"]["geometry"]["status"] == "pass"
    assert report["checks"]["feature_resolution"]["status"] == "pass"
    region = report["geometry_regions"][0]
    assert region["status"] == "pass"
    assert region["watertight"] is True
    assert region["winding_consistent"] is True
    assert region["signed_volume_m3"] == pytest.approx(0.24**3)
    assert region["sha256"] == hashlib.sha256(
        (tmp_path / "geometry" / "box.stl").read_bytes()
    ).hexdigest()
    assert report["problem"]["source_sha256"] == hashlib.sha256(problem.read_bytes()).hexdigest()
    json.dumps(report, allow_nan=False)


def test_missing_stl_fails_closed(tmp_path: Path) -> None:
    problem = _write_problem(tmp_path)
    (tmp_path / "geometry" / "box.stl").unlink()

    report = assess_geometry_preflight(problem)

    assert report["status"] == "fail"
    region = report["geometry_regions"][0]
    assert region["status"] == "fail"
    assert region["sha256"] is None
    assert "missing_stl" in region["reasons"]


def test_ten_millimetre_declared_feature_on_forty_millimetre_grid_fails(
    tmp_path: Path,
) -> None:
    problem = _write_problem(tmp_path, feature_policy={"minimum_solid_width_m": 0.01})

    report = assess_geometry_preflight(problem)

    feature = report["checks"]["feature_resolution"]["features"][0]
    assert report["status"] == "fail"
    assert report["checks"]["feature_resolution"]["status"] == "fail"
    assert feature["represented_cells"] == pytest.approx(0.25)
    assert feature["required_cells"] == pytest.approx(3.0)
    assert any("subgrid" in reason for reason in feature["reasons"])


def test_feature_at_required_resolution_passes(tmp_path: Path) -> None:
    problem = _write_problem(
        tmp_path,
        feature_policy={
            "minimum_solid_width_m": 0.12,
            "minimum_void_width_m": 0.12,
            "minimum_gap_m": 0.12,
            "erosion_radius_m": 0.04,
        },
    )

    report = assess_geometry_preflight(problem, minimum_cells_per_feature=3)

    assert report["status"] == "pass"
    assert all(
        item["status"] == "pass"
        for item in report["checks"]["feature_resolution"]["features"]
    )


def test_degenerate_mesh_fails_closed(tmp_path: Path) -> None:
    problem = _write_problem(tmp_path)
    degenerate = trimesh.Trimesh(
        vertices=np.array(
            [
                [0.0, 0.0, 0.0],
                [0.1, 0.0, 0.0],
                [0.0, 0.0, 0.0],
            ],
            dtype=np.float64,
        ),
        faces=np.array([[0, 1, 2]], dtype=np.int64),
        process=False,
    )
    degenerate.export(tmp_path / "geometry" / "box.stl")

    report = assess_geometry_preflight(problem)

    assert report["status"] == "fail"
    region = report["geometry_regions"][0]
    assert region["status"] == "fail"
    assert region["degenerate_face_count"] == 1
    assert "degenerate_faces" in region["reasons"]


def test_no_feature_policy_is_explicitly_not_evaluated(tmp_path: Path) -> None:
    report = assess_geometry_preflight(_write_problem(tmp_path))

    assert report["checks"]["geometry"]["status"] == "pass"
    assert report["checks"]["feature_resolution"]["status"] == "not_evaluated"
    assert report["checks"]["feature_resolution"]["evaluated"] is False
    assert report["status"] == "not_evaluated"


def test_invalid_problem_spec_fails_closed(tmp_path: Path) -> None:
    problem = tmp_path / "invalid.yaml"
    problem.write_text("schema_version: 999\n", encoding="utf-8")

    report = assess_geometry_preflight(problem)

    assert report["status"] == "fail"
    assert report["qualification"]["status"] == "fail"
    assert report["checks"]["problem_spec"]["status"] == "fail"
    assert report["problem"]["source_sha256"] == hashlib.sha256(
        problem.read_bytes()
    ).hexdigest()


def test_report_is_json_safe_and_marks_full_g3_unevaluated(tmp_path: Path) -> None:
    report = assess_geometry_preflight(_write_problem(tmp_path / "input"))

    json.dumps(report, allow_nan=False)
    assert report["qualification"]["status"] == "not_evaluated"
    assert "self_intersection" in report["scope"]["unimplemented_checks"]


def test_inconsistent_winding_fails_closed(tmp_path: Path) -> None:
    problem = _write_problem(tmp_path)
    mesh = trimesh.creation.box(extents=(0.24, 0.24, 0.24))
    mesh.faces[0] = mesh.faces[0][::-1]
    mesh._cache.clear()
    mesh.export(tmp_path / "geometry" / "box.stl")

    report = assess_geometry_preflight(problem)

    region = report["geometry_regions"][0]
    assert report["status"] == "fail"
    assert region["winding_consistent"] is False
    assert "inconsistent_winding" in region["reasons"]
