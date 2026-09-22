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
