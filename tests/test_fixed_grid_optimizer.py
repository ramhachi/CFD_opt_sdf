from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv

from cfd_sdf.fixed_grid_contract import (
    FIXED_GRID_CONTRACT_SCHEMA_VERSION,
    CartesianCellGrid,
    _write_cell_vti,
)
from cfd_sdf.fixed_grid_optimizer import (
    FixedGridOptimizerControls,
    run_fixed_grid_constrained_density_step,
)


def test_fixed_grid_constrained_step_moves_downforce_descent_direction(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(tmp_path / "contract", rho_value=0.4)
    sensitivity = _write_sensitivity(
        tmp_path / "sensitivity",
        downforce=np.array([2.0, 0.0, 0.0, 0.0], dtype=np.float32),
    )

    result = run_fixed_grid_constrained_density_step(
        topology_state,
        sensitivity_vti=sensitivity,
        output_dir=tmp_path / "step",
        controls=FixedGridOptimizerControls(
            move_limit=0.1,
            enforce_efficiency=False,
            enforce_connectivity=False,
            enforce_volume=False,
        ),
    )

    assert result.accepted_by_linearization is True
    density = pv.read(result.output_density_vti).cell_data["rho"]
    assert density[0] == pytest.approx(0.5)
    assert np.allclose(density[1:], 0.4)


def test_fixed_grid_constrained_step_projects_volume_constraint(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(tmp_path / "contract", rho_value=0.5)
    sensitivity = _write_sensitivity(
        tmp_path / "sensitivity",
        downforce=np.ones(4, dtype=np.float32),
    )

    result = run_fixed_grid_constrained_density_step(
        topology_state,
        sensitivity_vti=sensitivity,
        output_dir=tmp_path / "step",
        controls=FixedGridOptimizerControls(
            move_limit=0.1,
            volume_fraction_min=0.0,
            volume_fraction_max=0.5,
            enforce_efficiency=False,
            enforce_connectivity=False,
            enforce_volume=True,
        ),
    )

    assert result.accepted_by_linearization is True
    density = pv.read(result.output_density_vti).cell_data["rho"]
    assert float(np.mean(density)) <= 0.500001
    assert result.summary["linearized_constraints_ok"] is True


def test_fixed_grid_constrained_step_slsqp_backend_respects_efficiency_constraint(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(tmp_path / "contract", rho_value=0.5)
    sensitivity = _write_sensitivity(
        tmp_path / "sensitivity",
        downforce=np.ones(4, dtype=np.float32),
        efficiency=np.ones(4, dtype=np.float32),
        efficiency_constraint=0.0,
    )

    result = run_fixed_grid_constrained_density_step(
        topology_state,
        sensitivity_vti=sensitivity,
        output_dir=tmp_path / "step",
        controls=FixedGridOptimizerControls(
            optimizer_backend="slsqp-linearized",
            move_limit=0.1,
            enforce_efficiency=True,
            enforce_connectivity=False,
            enforce_volume=False,
        ),
    )

    assert result.accepted_by_linearization is True
    assert result.summary["optimizer_backend"]["name"] == "slsqp-linearized"
    efficiency = next(
        item
        for item in result.summary["linearized_constraints"]
        if item["name"] == "efficiency"
    )
    assert efficiency["predicted_violation"] <= 1.0e-8
    density = pv.read(result.output_density_vti).cell_data["rho"]
    assert float(np.sum(density - 0.5)) <= 1.0e-7


def test_fixed_grid_constrained_step_rejects_sampled_connectivity_derivatives(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(tmp_path / "contract", rho_value=0.5)
    sensitivity = _write_sensitivity(
        tmp_path / "sensitivity",
        downforce=np.zeros(4, dtype=np.float32),
        connectivity_nominal=np.ones(4, dtype=np.float32),
        connectivity_eroded=np.ones(4, dtype=np.float32),
        sample_mask=np.array([1, 0, 0, 0], dtype=np.uint8),
        connectivity_status="finite_difference_reference_sampled",
    )

    with pytest.raises(ValueError, match="sampled connectivity derivatives"):
        run_fixed_grid_constrained_density_step(
            topology_state,
            sensitivity_vti=sensitivity,
            output_dir=tmp_path / "step",
            controls=FixedGridOptimizerControls(
                enforce_efficiency=False,
                enforce_connectivity=True,
                enforce_volume=False,
            ),
        )


def _write_transform_declaration(
    path: Path,
    *,
    filter_kind: str = "identity",
    radius_m: float = 1.0,
    projection_b: float = 0.0,
    ramp_q: float = 0.0,
    volume_limit: float | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "kind": "design_transform_declaration",
        "schema_version": 1,
        "filter": {"kind": filter_kind, "spacing_m": 1.0, "radius_m": radius_m},
        "projection": {"b": projection_b, "eta": 0.5},
        "ramp": {"q": ramp_q},
        "volume_budget": (
            {"constraint_id": "volume_fraction_max", "limit": volume_limit}
            if volume_limit is not None
            else None
        ),
    }
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def test_fixed_grid_constrained_step_uses_compiled_problem_spec(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(tmp_path / "contract", rho_value=0.4)
    sensitivity = _write_sensitivity(
        tmp_path / "sensitivity",
        downforce=np.zeros(4, dtype=np.float32),
        drag=np.ones(4, dtype=np.float32),
        dry_coefficients={"drag_coefficient": 2.0, "downforce_coefficient": 0.1},
    )
    spec_path = _write_problem_spec(tmp_path / "spec.yaml", sense="minimize", response_id="drag")
    declaration = _write_transform_declaration(tmp_path / "transform.json")

    result = run_fixed_grid_constrained_density_step(
        topology_state,
        sensitivity_vti=sensitivity,
        output_dir=tmp_path / "step",
        controls=FixedGridOptimizerControls(
            move_limit=0.1,
            enforce_efficiency=False,
            enforce_connectivity=False,
            enforce_volume=False,
        ),
        problem_spec_json=spec_path,
        transform_declaration_json=declaration,
    )

    assert result.summary["problem"]["objective_source"] == "problem_spec_compiler"
    assert result.summary["problem"]["objectives"][0]["id"] == "declared_objective"
    assert result.summary["objective"]["base_objective"] == pytest.approx(2.0)
    assert result.summary["declared_equals_solved"] is True
    assert result.summary["solved_set"]["volume"] is None
    assert result.summary["transform"]["transform_hash"]
    assert result.summary["transform"]["declaration_hash"]
    density = pv.read(result.output_density_vti).cell_data["rho"]
    assert np.allclose(density, 0.3)


def test_fixed_grid_constrained_step_rejects_undeclared_response_gradient(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(tmp_path / "contract", rho_value=0.4)
    sensitivity = _write_sensitivity(
        tmp_path / "sensitivity",
        downforce=np.ones(4, dtype=np.float32),
    )
    spec_path = _write_problem_spec(tmp_path / "spec.yaml", sense="minimize", response_id="lift")
    declaration = _write_transform_declaration(tmp_path / "transform.json")

    with pytest.raises(ValueError, match="missing arrays"):
        run_fixed_grid_constrained_density_step(
            topology_state,
            sensitivity_vti=sensitivity,
            output_dir=tmp_path / "step",
            controls=FixedGridOptimizerControls(
                enforce_efficiency=False,
                enforce_connectivity=False,
                enforce_volume=False,
            ),
            problem_spec_json=spec_path,
            transform_declaration_json=declaration,
        )


def test_production_solved_set_is_compiler_only_and_transform_owned(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(tmp_path / "contract", rho_value=0.4)
    sensitivity = _write_sensitivity(
        tmp_path / "sensitivity",
        downforce=np.zeros(4, dtype=np.float32),
        drag=np.ones(4, dtype=np.float32),
        dry_coefficients={"drag_coefficient": 2.0, "downforce_coefficient": 0.1},
    )
    spec_path = _write_problem_spec(tmp_path / "spec.yaml", sense="minimize", response_id="drag")
    declaration = _write_transform_declaration(
        tmp_path / "transform.json",
        filter_kind="cone",
        radius_m=1.0,
        projection_b=4.0,
        ramp_q=30.0,
        volume_limit=0.5,
    )

    result = run_fixed_grid_constrained_density_step(
        topology_state,
        sensitivity_vti=sensitivity,
        output_dir=tmp_path / "step",
        controls=FixedGridOptimizerControls(
            move_limit=0.1,
            enforce_efficiency=False,
            enforce_connectivity=False,
            enforce_volume=False,
        ),
        problem_spec_json=spec_path,
        transform_declaration_json=declaration,
    )

    summary = result.summary
    assert summary["declared_equals_solved"] is True
    assert summary["solved_set"]["volume"]["limit"] == pytest.approx(0.5)
    assert summary["solved_set"]["volume"]["source"] == "compile_time_declaration"
    assert any(
        "enforce_volume=False" in item for item in summary["ignored_legacy_controls"]
    )
    # the derived arrays come from the declared transform, not identity copies
    from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection

    active = np.ones(4, dtype=bool)
    transform = DesignTransform(
        shape=(4, 1, 1),
        spacing_m=1.0,
        active_mask=active,
        filter=ConeFilter(shape=(4, 1, 1), spacing_m=1.0, active_mask=active, radius_m=1.0),
        projection=TanhProjection(4.0, 0.5),
        ramp=RampInterpolation(30.0),
    )
    assert summary["transform"]["transform_hash"] == transform.transform_hash()
    semantic = summary["semantic_names"]
    assert "recomputed" in semantic["rho_projection"]
    assert "rho_projected" in semantic["beta_solver"]
    assert "beta_max" in semantic["brinkman_alpha"]
    density = pv.read(result.output_density_vti).cell_data
    candidate_rho = np.asarray(density["rho"], dtype=np.float64)
    expected = transform.forward(candidate_rho)
    assert np.allclose(np.asarray(density["rho_filtered"], dtype=np.float64), expected.rho_filtered, atol=1e-6)
    assert np.allclose(np.asarray(density["rho_projected"], dtype=np.float64), expected.beta, atol=1e-6)


def test_production_path_fails_closed_on_undeclared_or_diagnostic_declarations(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(tmp_path / "contract", rho_value=0.4)
    sensitivity = _write_sensitivity(
        tmp_path / "sensitivity",
        downforce=np.ones(4, dtype=np.float32),
        dry_coefficients={"drag_coefficient": 1.0, "downforce_coefficient": 0.0},
    )
    spec_path = _write_problem_spec(tmp_path / "spec.yaml", sense="minimize", response_id="drag")

    with pytest.raises(ValueError, match="design-transform"):
        run_fixed_grid_constrained_density_step(
            topology_state,
            sensitivity_vti=sensitivity,
            output_dir=tmp_path / "no_declaration",
            controls=FixedGridOptimizerControls(
                enforce_efficiency=False, enforce_connectivity=False, enforce_volume=False
            ),
            problem_spec_json=spec_path,
        )

    block_declaration = _write_transform_declaration(
        tmp_path / "block.json", filter_kind="block"
    )
    with pytest.raises(ValueError, match="block filter"):
        run_fixed_grid_constrained_density_step(
            topology_state,
            sensitivity_vti=sensitivity,
            output_dir=tmp_path / "block",
            controls=FixedGridOptimizerControls(
                enforce_efficiency=False, enforce_connectivity=False, enforce_volume=False
            ),
            problem_spec_json=spec_path,
            transform_declaration_json=block_declaration,
        )

    no_budget = _write_transform_declaration(tmp_path / "no_budget.json")
    with pytest.raises(ValueError, match="undeclared constraints"):
        run_fixed_grid_constrained_density_step(
            topology_state,
            sensitivity_vti=sensitivity,
            output_dir=tmp_path / "implicit_volume",
            controls=FixedGridOptimizerControls(
                enforce_efficiency=False, enforce_connectivity=False, enforce_volume=True
            ),
            problem_spec_json=spec_path,
            transform_declaration_json=no_budget,
        )


def _write_problem_spec(path: Path, *, sense: str, response_id: str) -> Path:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 2,
        "problem_id": "optimizer_compiler_fixture",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        },
        "grid": {"kind": "uniform_cartesian", "voxel_size_m": 1.0, "padding_m": 0.0},
        "geometry_regions": [
            {"id": "design_box", "role": "design_domain", "file": "geometry/design_box.stl"}
        ],
        "flow_cases": [
            {
                "id": "straight",
                "freestream_velocity_mps": [30.0, 0.0, 0.0],
                "fluid": {
                    "model": "incompressible_newtonian",
                    "density_kg_m3": 1.225,
                    "dynamic_viscosity_pa_s": 1.8e-5,
                },
                "turbulence": {"model": "k_omega_sst"},
                "boundary_conditions": {"inlet": "freestream", "outlet": "pressure_outlet"},
                "motion_profiles": {},
            }
        ],
        "responses": [
            {"id": "drag", "kind": "force", "flow_case_id": "straight", "direction": [1.0, 0.0, 0.0]},
            {"id": "downforce", "kind": "force", "flow_case_id": "straight", "direction": [0.0, 0.0, -1.0]},
            {"id": "lift", "kind": "force", "flow_case_id": "straight", "direction": [0.0, 0.0, 1.0]},
        ],
        "objectives": [
            {
                "id": "declared_objective",
                "sense": sense,
                "terms": [
                    {"coefficient": 1.0, "flow_case_id": "straight", "response_id": response_id}
                ],
            }
        ],
        "constraints": [],
        "topology_policy": {
            "minimum_solid_width_m": None,
            "minimum_void_width_m": None,
            "minimum_gap_m": None,
            "erosion_radius_m": None,
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
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _write_topology_state(directory: Path, *, rho_value: float) -> Path:
    directory.mkdir(parents=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0),
        spacing=(1.0, 1.0, 1.0),
        cell_shape=(4, 1, 1),
    )
    count = grid.cell_count
    rho = np.full(count, rho_value, dtype=np.float32)
    arrays = {
        "rho": rho,
        "rho_filtered": rho.copy(),
        "rho_projected": rho.copy(),
        "alpha": (100.0 * rho).astype(np.float32),
        "allowed_mask": np.ones(count, dtype=np.uint8),
        "forbidden_mask": np.zeros(count, dtype=np.uint8),
        "fixed_solid_mask": np.zeros(count, dtype=np.uint8),
        "root_mask": np.zeros(count, dtype=np.uint8),
        "active_design_mask": np.ones(count, dtype=np.uint8),
    }
    _write_cell_vti(grid, arrays, directory / "density.vti", kind="fixed_grid_density")
    state = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "density_vti": "density.vti",
        "source_solver": {"backend": "test"},
    }
    path = directory / "topology_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def _write_sensitivity(
    directory: Path,
    *,
    downforce: np.ndarray,
    drag: np.ndarray | None = None,
    efficiency: np.ndarray | None = None,
    efficiency_constraint: float = -1.0,
    dry_coefficients: dict[str, float] | None = None,
    connectivity_nominal: np.ndarray | None = None,
    connectivity_eroded: np.ndarray | None = None,
    sample_mask: np.ndarray | None = None,
    connectivity_status: str = "finite_difference_reference_full",
) -> Path:
    directory.mkdir(parents=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0),
        spacing=(1.0, 1.0, 1.0),
        cell_shape=(4, 1, 1),
    )
    count = grid.cell_count
    nominal = (
        np.zeros(count, dtype=np.float32)
        if connectivity_nominal is None
        else connectivity_nominal.astype(np.float32)
    )
    eroded = (
        np.zeros(count, dtype=np.float32)
        if connectivity_eroded is None
        else connectivity_eroded.astype(np.float32)
    )
    arrays = {
        "d_downforce_d_rho": downforce.astype(np.float32),
        "d_drag_d_rho": (
            np.zeros(count, dtype=np.float32)
            if drag is None
            else drag.astype(np.float32)
        ),
        "d_efficiency_constraint_d_rho": (
            np.zeros(count, dtype=np.float32)
            if efficiency is None
            else efficiency.astype(np.float32)
        ),
        "d_connectivity_nominal_d_rho": nominal,
        "d_connectivity_eroded_d_rho": eroded,
        "active_design_mask": np.ones(count, dtype=np.uint8),
    }
    if sample_mask is not None:
        arrays["connectivity_derivative_sample_mask"] = sample_mask.astype(np.uint8)
    sensitivity_vti = directory / "fixed_grid_sensitivity.vti"
    _write_cell_vti(
        grid,
        arrays,
        sensitivity_vti,
        kind="fixed_grid_sensitivity",
    )
    summary = {
        "schema_version": 1,
        "kind": "fixed_grid_sensitivity_summary",
        "roadmap_phase": "T5-test",
        "connectivity_derivative_status": connectivity_status,
        "primal_values": {
            "objective": 0.0,
            "efficiency_constraint": efficiency_constraint,
            **(dry_coefficients or {}),
        },
        "base_objectives": {
            "connectivity_nominal_violation_l1": 1.0,
            "connectivity_eroded_violation_l1": 1.0,
        },
    }
    (directory / "fixed_grid_sensitivity_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    return sensitivity_vti
