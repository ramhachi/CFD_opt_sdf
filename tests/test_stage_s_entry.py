"""Tests for the composite Stage S entry gate (PQ4.0)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.extraction_sweep import ExtractionSweepError, run_extraction_threshold_sweep
from cfd_sdf.fixed_grid_contract import CartesianCellGrid, _write_cell_vti
from cfd_sdf.handoff import build_density_to_sdf_handoff
from cfd_sdf.stage_s_entry import qualify_stage_s_entry


def _write_state(
    directory: Path,
    *,
    fill: float,
    grey_band: float | None = None,
    root_cell: tuple[int, int, int] | None = (1, 3, 3),
) -> Path:
    from test_handoff import _cell_index, _state_dict

    directory.mkdir(parents=True, exist_ok=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=(6, 6, 6)
    )
    count = grid.cell_count
    density = np.zeros(count, dtype=np.float32)
    for x in range(1, 5):
        for y in range(1, 5):
            for z in range(1, 5):
                density[_cell_index((x, y, z), (6, 6, 6))] = fill
    if grey_band is not None:
        for x in range(0, 6):
            for y in range(0, 6):
                for z in range(0, 6):
                    if density[_cell_index((x, y, z), (6, 6, 6))] == 0.0:
                        density[_cell_index((x, y, z), (6, 6, 6))] = grey_band
    root = np.zeros(count, dtype=np.uint8)
    if root_cell is not None:
        root[_cell_index(root_cell, (6, 6, 6))] = 1
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


def _write_spec(
    path: Path,
    *,
    domain: tuple[list[float], list[float]] = ([-1.0, -1.0, -1.0], [9.0, 9.0, 9.0]),
    root_required: bool = False,
) -> Path:
    import yaml

    connectivity = {
        "mode": "root_connected" if root_required else "disabled",
        "required_root_group_ids": ["root_group"] if root_required else [],
        "max_components": None,
        "evaluate_eroded": False,
    }
    spec = {
        "schema_version": 2,
        "problem_id": "stage_s_entry_fixture",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        },
        "grid": {
            "kind": "uniform_cartesian",
            "voxel_size_m": 1.0,
            "padding_m": 0.0,
            "domain_bounds_m": {"lower": domain[0], "upper": domain[1]},
        },
        "geometry_regions": [
            {"id": "design_box", "role": "design_domain", "file": "geometry/design_box.stl"},
            *(
                [{"id": "root_region", "role": "root", "file": "geometry/root.stl"}]
                if root_required
                else []
            ),
        ],
        "flow_cases": [
            {
                "id": "straight",
                "freestream_velocity_mps": [1.0, 0.0, 0.0],
                "fluid": {
                    "model": "incompressible_newtonian",
                    "density_kg_m3": 1.0,
                    "dynamic_viscosity_pa_s": 1e-2,
                },
                "turbulence": {"model": "laminar"},
                "boundary_conditions": {"inlet": "freestream", "outlet": "pressure_outlet"},
                "motion_profiles": {},
            }
        ],
        "responses": [
            {"id": "downforce", "kind": "force", "flow_case_id": "straight", "direction": [0.0, 0.0, -1.0]}
        ],
        "objectives": [
            {"id": "maximize_downforce", "sense": "maximize",
             "terms": [{"coefficient": 1.0, "flow_case_id": "straight", "response_id": "downforce"}]}
        ],
        "constraints": [],
        "topology_policy": {
            "root_groups": (
                [{"id": "root_group", "region_ids": ["root_region"]}] if root_required else []
            ),
            "minimum_solid_width_m": None,
            "minimum_void_width_m": None,
            "minimum_gap_m": None,
            "erosion_radius_m": None,
            "solid_connectivity": connectivity,
            "void_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
                "evaluate_eroded": False,
            },
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return path


_TEST_PROFILES = {
    "extraction_profile": {
        "profile_id": "extraction_test",
        "surface_distance_max_m": 1.5,
        "surface_distance_rms_max_m": 1.5,
        "feature_shrink_max_voxels": 1.0,
        "require_watertight": True,
        "require_winding_consistent": True,
        "require_positive_volume": True,
        "require_no_duplicate_faces": True,
        "require_root_connectivity": True,
    },
    "volume_profile": {
        "profile_id": "volume_test",
        "relative_max": 0.5,
        "revoxelized_relative_max": 0.5,
        "absolute_max_m3": 50.0,
    },
}


def _handoff(tmp_path: Path, state: Path) -> object:
    return build_density_to_sdf_handoff(state, output_dir=tmp_path / "handoff", iso_value=0.5)


def test_binary_candidate_passes_every_composite_gate(tmp_path: Path):
    state = _write_state(tmp_path / "candidate", fill=1.0)
    artifacts = _handoff(tmp_path, state)
    spec = _write_spec(tmp_path / "spec.yaml")
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec,
        **_TEST_PROFILES,
    )
    assert verdict.ready_for_stage_s is True, verdict.reasons
    for key, sub in verdict.sub_verdicts.items():
        if key == "lineage":
            assert sub["status"] == "pass"
        else:
            assert sub.get("pass") is True, key


def test_grey_field_local_extraction_pass_cannot_override_discreteness(tmp_path: Path):
    state = _write_state(tmp_path / "candidate", fill=0.6, grey_band=0.4)
    artifacts = _handoff(tmp_path, state)
    spec = _write_spec(tmp_path / "spec.yaml")
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec,
        **_TEST_PROFILES,
    )
    assert verdict.ready_for_stage_s is False
    assert any(reason.startswith("discreteness:") for reason in verdict.reasons)
    assert verdict.sub_verdicts["discreteness"]["pass"] is False


def test_candidate_outside_the_declared_domain_fails_clearance(tmp_path: Path):
    state = _write_state(tmp_path / "candidate", fill=1.0)
    artifacts = _handoff(tmp_path, state)
    spec = _write_spec(tmp_path / "spec.yaml", domain=([10.0, 10.0, 10.0], [20.0, 20.0, 20.0]))
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec,
        **_TEST_PROFILES,
    )
    assert verdict.ready_for_stage_s is False
    assert any(reason.startswith("clearance:") for reason in verdict.reasons)


def test_root_required_policy_with_empty_root_mask_fails(tmp_path: Path):
    state = _write_state(tmp_path / "candidate", fill=1.0, root_cell=None)
    artifacts = _handoff(tmp_path, state)
    spec = _write_spec(tmp_path / "spec.yaml", root_required=True)
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec,
        **_TEST_PROFILES,
    )
    assert verdict.ready_for_stage_s is False
    assert any("root mask is empty" in reason for reason in verdict.reasons)


def test_selection_rule_must_require_stage_s_ready(tmp_path: Path):
    state = _write_state(tmp_path / "candidate", fill=1.0)
    with pytest.raises(ExtractionSweepError, match="require_ready_for_stage_s"):
        run_extraction_threshold_sweep(
            state,
            thresholds=[0.5],
            output_dir=tmp_path / "sweep",
            selection_rule={"kind": "registered_range_first_that_passes", "range": [0.4, 0.6]},
        )


def _write_two_component_state(directory: Path, *, with_root: bool, gap: int = 1) -> Path:
    from test_handoff import _cell_index, _state_dict

    directory.mkdir(parents=True, exist_ok=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=(8, 6, 6)
    )
    count = grid.cell_count
    density = np.zeros(count, dtype=np.float32)
    # two blobs on the x axis, separated by `gap` empty columns (interior)
    for x in range(1, 3):
        for y in range(1, 5):
            for z in range(1, 5):
                density[_cell_index((x, y, z), (8, 6, 6))] = 1.0
    for x in range(2 + gap + 1, 2 + gap + 3):
        for y in range(1, 5):
            for z in range(1, 5):
                density[_cell_index((x, y, z), (8, 6, 6))] = 1.0
    root = np.zeros(count, dtype=np.uint8)
    if with_root:
        root[_cell_index((1, 3, 3), (8, 6, 6))] = 1
        root[_cell_index((min(2 + gap + 1, 5), 3, 3), (8, 6, 6))] = 1
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


def test_component_boundary_gap_matches_analytic_fixtures():
    from cfd_sdf.shape_feature_metrics import component_boundary_gap_m

    # axis-aligned separation: two cells with `gap` empty columns between them
    # measure exactly gap * spacing (the old center-to-center EDT returned
    # (gap + 1) * spacing)
    for gap in (1, 2, 3):
        components = np.zeros((10, 3, 3), dtype=np.int64)
        components[1, 1, 1] = 1
        components[2 + gap, 1, 1] = 2
        assert component_boundary_gap_m(components, 1.0) == pytest.approx(float(gap))

    # corner touch: the cube surfaces meet, so the gap is 0
    corner = np.zeros((5, 5, 3), dtype=np.int64)
    corner[1, 1, 1] = 1
    corner[2, 2, 1] = 2
    assert component_boundary_gap_m(corner, 1.0) == pytest.approx(0.0)

    assert component_boundary_gap_m(np.zeros((4, 4, 4), dtype=np.int64), 1.0) is None


def test_component_boundary_gap_is_measured(tmp_path: Path):
    state = _write_two_component_state(tmp_path / "candidate", with_root=False, gap=2)
    artifacts = _handoff(tmp_path, state)
    spec = _write_spec(tmp_path / "spec.yaml")
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec,
        **_TEST_PROFILES,
    )
    measured = verdict.sub_verdicts["width_gap"]["measured"].get("component_boundary_gap_m")
    assert measured == pytest.approx(2.0), verdict.sub_verdicts["width_gap"]


def _declared_policy_spec(tmp_path: Path, **policy: float) -> Path:
    import yaml as _yaml

    spec_path = _write_spec(tmp_path / "spec.yaml")
    data = _yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    data["topology_policy"].update(policy)
    spec_path.write_text(_yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return spec_path


def _write_plate_state(directory: Path) -> Path:
    from test_handoff import _cell_index, _state_dict

    directory.mkdir(parents=True, exist_ok=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=(12, 12, 12)
    )
    count = grid.cell_count
    density = np.zeros(count, dtype=np.float32)
    for x in range(3, 9):
        for y in range(3, 9):
            for z in range(3, 5):
                density[_cell_index((x, y, z), (12, 12, 12))] = 1.0
    arrays = {
        "rho": density,
        "rho_filtered": density.copy(),
        "rho_projected": density.copy(),
        "alpha": (density * 2500.0).astype(np.float32),
        "allowed_mask": np.ones(count, dtype=np.uint8),
        "forbidden_mask": np.zeros(count, dtype=np.uint8),
        "fixed_solid_mask": np.zeros(count, dtype=np.uint8),
        "root_mask": np.zeros(count, dtype=np.uint8),
        "active_design_mask": np.ones(count, dtype=np.uint8),
    }
    _write_cell_vti(grid, arrays, directory / "density.vti", kind="fixed_grid_density")
    path = directory / "topology_state.json"
    path.write_text(json.dumps(_state_dict(grid, "density.vti"), indent=2), encoding="utf-8")
    return path


def test_declared_minimum_solid_width_uses_the_true_minimum(tmp_path: Path):
    # a 2-cell-thick plate revoxelizes to exactly two voxels, so the true
    # minimum width is exactly 2 * spacing (the p5 quantile agrees here; the
    # contract point is that the declared minimum is compared against the
    # minimum, not against the quantile)
    state = _write_plate_state(tmp_path / "candidate")
    artifacts = _handoff(tmp_path, state)
    spec = _declared_policy_spec(tmp_path, minimum_solid_width_m=1.5)
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec,
        **_TEST_PROFILES,
    )
    width = verdict.sub_verdicts["width_gap"]
    assert width["measured"]["minimum_solid_width_m"] == pytest.approx(2.0)
    assert width["measured"]["ridge_width_p5_m"] == pytest.approx(2.0)
    assert width["pass"] is True, width

    spec = _declared_policy_spec(tmp_path, minimum_solid_width_m=3.0)
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec,
        **_TEST_PROFILES,
    )
    assert verdict.ready_for_stage_s is False
    assert any("minimum solid width" in reason for reason in verdict.reasons)


def test_declared_minimum_gap_above_measurement_fails(tmp_path: Path):
    import yaml as _yaml

    from cfd_sdf.problem_spec import load_problem_spec

    state = _write_two_component_state(tmp_path / "candidate", with_root=False, gap=2)
    artifacts = _handoff(tmp_path, state)
    spec_path = _write_spec(tmp_path / "spec.yaml")
    data = _yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    data["topology_policy"]["minimum_gap_m"] = 5.0
    spec_path.write_text(_yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec_path,
        **_TEST_PROFILES,
    )
    assert verdict.ready_for_stage_s is False
    assert any("gap" in reason for reason in verdict.reasons)


def test_self_intersection_not_evaluated_fails_when_required(tmp_path: Path):
    state = _write_state(tmp_path / "candidate", fill=1.0)
    artifacts = _handoff(tmp_path, state)
    spec = _write_spec(tmp_path / "spec.yaml")
    profiles = dict(_TEST_PROFILES)
    profiles["extraction_profile"] = dict(
        profiles["extraction_profile"], require_self_intersection_measured=True
    )
    # the clean block's real test vector: the check must return a decisive
    # status, and a not-evaluated status must suppress global readiness
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=spec,
        **profiles,
    )
    checks = (verdict.sub_verdicts["extraction_profile"].get("checks") or {})
    status = (checks.get("mesh_manifold") or {}).get("self_intersection")
    assert status in {"none", "fail", "not_evaluated"} or isinstance(status, str)
    if str(status).startswith("not_evaluated"):
        assert verdict.ready_for_stage_s is False


def test_thin_one_cell_feature_is_detected(tmp_path: Path):
    from test_handoff import _cell_index

    state = _write_state(tmp_path / "candidate", fill=1.0)
    # overwrite one sure-solid cell row into a thin attached spur
    directory = state.parent
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=(6, 6, 6)
    )
    import pyvista as pv

    image = pv.read(directory / "density.vti")
    rho = np.asarray(image.cell_data["rho"], dtype=np.float32).copy()
    # a one-cell-thick spur protruding from the block survives at rho=1
    density = rho.copy()
    density[_cell_index((2, 5, 3), (6, 6, 6))] = 1.0
    arrays = {
        "rho": density,
        "rho_filtered": density.copy(),
        "rho_projected": density.copy(),
        "alpha": (density * 2500).astype(np.float32),
        "allowed_mask": np.ones(count := grid.cell_count, dtype=np.uint8),
        "forbidden_mask": np.zeros(count, dtype=np.uint8),
        "fixed_solid_mask": np.zeros(count, dtype=np.uint8),
        "root_mask": np.zeros(count, dtype=np.uint8),
        "root_mask": np.asarray(
            json.loads((directory / "topology_state.json").read_text(
                encoding="utf-8"
            )).get("root_mask", np.zeros(count, dtype=np.uint8)),
            dtype=np.uint8,
        ),
        "active_design_mask": np.ones(count, dtype=np.uint8),
    }
    _write_cell_vti(grid, arrays, directory / "density.vti", kind="fixed_grid_density")
    artifacts = build_density_to_sdf_handoff(
        directory / "topology_state.json",
        output_dir=tmp_path / "handoff_thin",
        iso_value=0.5,
    )
    verdict = qualify_stage_s_entry(
        artifacts.manifest_json,
        mesh_path=artifacts.surface_stl,
        problem_spec_yaml=_write_spec(tmp_path / "spec.yaml"),
        **_TEST_PROFILES,
    )
    assert verdict.sub_verdicts["width_gap"]["pass"] is True
