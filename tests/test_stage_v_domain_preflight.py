from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
import yaml

from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256
from cfd_sdf.sdf import build_fields
from cfd_sdf.stage_v_domain_preflight import (
    STAGE_V_CLEARANCE_PROFILE_V1,
    evaluate_stage_v_domain_preflight,
    write_stage_v_domain_preflight_report,
)

WORK_ROOT = Path(__file__).resolve().parents[1] / "work" / "filtered_ramp" / "wmin_0.2" / "export"
CORRECT_CANDIDATE_STL = WORK_ROOT / "opt_q100_b0_step0_try0_block" / "iso_surface.stl"
WRONG_CANDIDATE_STL = WORK_ROOT / "opt_q100_b0_step5_try1_block_keep_round" / "iso_surface.stl"

DOMAIN_LOWER = (-1.0, -0.8, -0.6)
DOMAIN_UPPER = (2.0, 0.8, 0.6)


def _box(path: Path, center, extents) -> None:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)


def _spec_dict() -> dict:
    return {
        "schema_version": 2,
        "problem_id": "stage_v_domain_preflight_fixture",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        },
        "grid": {
            "kind": "uniform_cartesian",
            "voxel_size_m": 0.05,
            "padding_m": 0.0,
            "domain_bounds_m": {"lower": list(DOMAIN_LOWER), "upper": list(DOMAIN_UPPER)},
        },
        "reference_values": {"area_m2": 0.64, "length_m": 0.8, "moment_center_m": [0.25, 0.0, 0.0]},
        "geometry_regions": [
            {"id": "design_domain", "role": "design_domain", "file": "geometry/design_domain.stl"},
        ],
        "flow_cases": [
            {
                "id": "matched_re_laminar",
                "freestream_velocity_mps": [1.0, 0.0, 0.0],
                "fluid": {"model": "incompressible_newtonian", "density_kg_m3": 1.0, "dynamic_viscosity_pa_s": 1.0e-02},
                "turbulence": {"model": "laminar"},
                "boundary_conditions": {"inlet": "freestream", "outlet": "pressure_outlet"},
                "motion_profiles": {},
            }
        ],
        "responses": [
            {"id": "drag", "kind": "force", "flow_case_id": "matched_re_laminar", "direction": [1.0, 0.0, 0.0]},
            {"id": "downforce", "kind": "force", "flow_case_id": "matched_re_laminar", "direction": [0.0, 0.0, -1.0]},
        ],
        "objectives": [
            {
                "id": "minimize_drag",
                "sense": "minimize",
                "terms": [{"coefficient": 1.0, "flow_case_id": "matched_re_laminar", "response_id": "drag"}],
            }
        ],
        "constraints": [],
        "topology_policy": {
            "root_groups": [],
            "solid_connectivity": {"mode": "disabled", "required_root_group_ids": [], "max_components": None, "evaluate_eroded": False},
            "void_connectivity": {"mode": "disabled", "required_root_group_ids": [], "max_components": None, "evaluate_eroded": False},
            "minimum_solid_width_m": None,
            "minimum_void_width_m": None,
            "minimum_gap_m": None,
            "erosion_radius_m": None,
        },
    }


def _write_spec(tmp_path: Path, **grid_updates) -> Path:
    data = _spec_dict()
    data["grid"].update(grid_updates)
    (tmp_path / "geometry").mkdir(parents=True, exist_ok=True)
    mesh = trimesh.creation.box(extents=(0.2, 0.2, 0.2))
    mesh.apply_translation((0.0, 0.0, 0.0))
    mesh.export(tmp_path / "geometry" / "design_domain.stl")
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return project_yaml


def _candidate(tmp_path: Path, name: str, lower, upper) -> Path:
    mesh = trimesh.creation.box(extents=np.asarray(upper) - np.asarray(lower))
    mesh.apply_translation((np.asarray(lower) + np.asarray(upper)) / 2.0)
    path = tmp_path / name
    mesh.export(path)
    return path


def test_missing_domain_bounds_fail_closed(tmp_path: Path) -> None:
    data = _spec_dict()
    del data["grid"]["domain_bounds_m"]
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    spec = load_problem_spec(project_yaml)
    stl = _candidate(tmp_path, "c.stl", (-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))

    preflight = evaluate_stage_v_domain_preflight(spec, stl, 0.05)

    assert not preflight.qualified
    assert "domain_bounds_missing" in preflight.reasons
    assert preflight.domain_bounds_m is None


def test_voxel_alignment_and_padding_fail_closed(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    stl = _candidate(tmp_path, "c.stl", (-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))

    preflight = evaluate_stage_v_domain_preflight(spec, stl, 0.15)

    assert not preflight.qualified
    assert "voxel_alignment_invalid" in preflight.reasons

    spec_pad = load_problem_spec(_write_spec(tmp_path, padding_m=0.1))
    preflight_pad = evaluate_stage_v_domain_preflight(spec_pad, stl, 0.05)
    assert not preflight_pad.qualified
    assert "grid_padding_m_must_be_zero_with_declared_domain" in preflight_pad.reasons


def test_candidate_outside_fixed_domain_fails(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    stl = _candidate(tmp_path, "outside.stl", (2.5, -0.1, -0.1), (2.8, 0.1, 0.1))

    preflight = evaluate_stage_v_domain_preflight(spec, stl, 0.05)

    assert not preflight.qualified
    assert "candidate_outside_fixed_domain" in preflight.reasons
    assert preflight.inside_fixed_box is False


def test_exact_boundary_contact_and_below_margin_fail(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    margin = STAGE_V_CLEARANCE_PROFILE_V1["minimum_clearance_m"]
    upper_z = DOMAIN_UPPER[2]
    contact = _candidate(tmp_path, "contact.stl", (-0.1, -0.1, upper_z - 0.2), (0.1, 0.1, upper_z))

    preflight = evaluate_stage_v_domain_preflight(spec, contact, 0.05)

    assert not preflight.qualified
    assert preflight.inside_fixed_box is True
    # binary STL stores float32: a plane-tangent candidate measures ~1e-7 m here
    assert abs(preflight.minimum_clearance_m_) <= 1.0e-5
    assert "clearance_below_declared_margin" in preflight.reasons
    assert preflight.limiting_patch is not None and preflight.limiting_patch.startswith("top")

    below = _candidate(
        tmp_path,
        "below.stl",
        (-0.1, -0.1, upper_z - margin * 0.5 - 0.1),
        (0.1, 0.1, upper_z - margin * 0.5),
    )
    preflight_below = evaluate_stage_v_domain_preflight(spec, below, 0.05)
    assert not preflight_below.qualified
    assert "clearance_below_declared_margin" in preflight_below.reasons


def test_just_passing_clearance_is_qualified(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    upper_z = DOMAIN_UPPER[2]
    passing = _candidate(
        tmp_path,
        "pass.stl",
        (-0.1, -0.1, upper_z - 0.31),
        (0.1, 0.1, upper_z - 0.26),
    )

    preflight = evaluate_stage_v_domain_preflight(spec, passing, 0.05)

    assert preflight.qualified
    assert preflight.limiting_patch == "top (upper_z)"
    assert preflight.minimum_clearance_m_ == pytest.approx(0.26)
    assert not preflight.reasons


def test_report_artifact_binds_hashes_and_patches(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    stl = _candidate(tmp_path, "bound.stl", (-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))

    preflight = evaluate_stage_v_domain_preflight(spec, stl, 0.05, flow_case_id="matched_re_laminar")
    report = write_stage_v_domain_preflight_report(tmp_path / "case_V1", preflight)

    doc = json.loads(report.read_text(encoding="utf-8"))
    assert doc["status"] == "pass"
    assert doc["qualified"] is True
    assert doc["qualification_profile"]["profile_id"] == "stage_v_clearance_v1"
    assert doc["qualification_profile"]["minimum_clearance_m"] == pytest.approx(0.25)
    assert doc["fixed_domain_binding"]["from_problem_spec_grid_domain_bounds_m"] is True
    assert doc["fixed_domain_binding"]["domain_bounds_m"]["lower"] == list(DOMAIN_LOWER)
    assert doc["candidate_stl_sha256"] == hashlib.sha256(stl.read_bytes()).hexdigest()
    assert doc["problem_spec_sha256"] == problem_spec_sha256(spec)
    assert doc["voxel_size_m"] == pytest.approx(0.05)
    assert sorted(doc["clearances_m"]) == sorted(
        ["inlet (lower_x)", "outlet (upper_x)", "sideMin (lower_y)", "sideMax (upper_y)", "bottom (lower_z)", "top (upper_z)"]
    )
    again = write_stage_v_domain_preflight_report(tmp_path / "case_V1", preflight)
    assert again.read_bytes() == report.read_bytes()


def test_fixed_domain_carries_through_case_generation(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    stl = _candidate(tmp_path / "geometry", "candidate.stl", (-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))

    config = problem_spec_to_project_config(spec, candidate_stl=stl, voxel_size_m=0.05)
    assert config.grid.domain_bounds_m == (DOMAIN_LOWER, DOMAIN_UPPER)

    bundle = build_fields(config)
    assert tuple(np.round(bundle.grid.bounds[0], 9)) == DOMAIN_LOWER
    assert tuple(np.round(bundle.grid.bounds[1], 9)) == DOMAIN_UPPER
    assert bundle.grid.shape == (61, 33, 25)

    case_dir = tmp_path / "case"
    generate_openfoam_case(config, bundle, case_dir)
    metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
    assert tuple(np.round(metadata["grid"]["bounds"][0], 9)) == DOMAIN_LOWER
    assert tuple(np.round(metadata["grid"]["bounds"][1], 9)) == DOMAIN_UPPER
    block_mesh = (case_dir / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert "(-1 -0.8 -0.6)" in block_mesh and "(2 0.8 0.6)" in block_mesh


def test_build_fields_refuses_misaligned_voxel_and_nonzero_padding(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    stl = _candidate(tmp_path / "geometry", "candidate.stl", (-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))

    misaligned = problem_spec_to_project_config(spec, candidate_stl=stl, voxel_size_m=0.15)
    with pytest.raises(ValueError, match="integer multiples"):
        build_fields(misaligned)

    config_pad = problem_spec_to_project_config(
        load_problem_spec(_write_spec(tmp_path, padding_m=0.1)), candidate_stl=stl
    )
    with pytest.raises(ValueError, match="padding_m"):
        build_fields(config_pad)


@pytest.mark.skipif(not CORRECT_CANDIDATE_STL.exists(), reason="recorded candidate STL not present on this machine")
def test_recorded_correct_candidate_passes_preflight() -> None:
    spec = load_problem_spec(WORK_ROOT.parent.parent.parent / "stage_sv_laminar" / "project_matched_re_laminar.yaml")

    for voxel in (0.05, 0.0125):
        preflight = evaluate_stage_v_domain_preflight(spec, CORRECT_CANDIDATE_STL, voxel)
        assert preflight.qualified, (voxel, preflight.reasons)
        assert preflight.minimum_clearance_m_ > STAGE_V_CLEARANCE_PROFILE_V1["minimum_clearance_m"]


@pytest.mark.skipif(not WRONG_CANDIDATE_STL.exists(), reason="recorded candidate STL not present on this machine")
def test_recorded_wrong_candidate_is_rejected_before_meshing(tmp_path: Path) -> None:
    spec = load_problem_spec(WORK_ROOT.parent.parent.parent / "stage_sv_laminar" / "project_matched_re_laminar.yaml")

    preflight = evaluate_stage_v_domain_preflight(spec, WRONG_CANDIDATE_STL, 0.0125)

    assert not preflight.qualified
    assert "clearance_below_declared_margin" in preflight.reasons
    assert preflight.minimum_clearance_m_ < STAGE_V_CLEARANCE_PROFILE_V1["minimum_clearance_m"]

    report = write_stage_v_domain_preflight_report(tmp_path / "V3_no_launch", preflight)
    doc = json.loads(report.read_text(encoding="utf-8"))
    assert doc["status"] == "fail" and doc["qualified"] is False
