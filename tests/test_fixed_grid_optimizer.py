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
    efficiency: np.ndarray | None = None,
    efficiency_constraint: float = -1.0,
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
        "d_drag_d_rho": np.zeros(count, dtype=np.float32),
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
