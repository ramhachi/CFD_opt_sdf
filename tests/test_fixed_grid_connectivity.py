from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyvista as pv

from cfd_sdf.fixed_grid_connectivity import (
    build_fixed_grid_connectivity_derivatives,
    build_fixed_grid_connectivity_state,
    evaluate_fixed_grid_connectivity_objectives,
)
from cfd_sdf.fixed_grid_contract import (
    FIXED_GRID_CONTRACT_SCHEMA_VERSION,
    CartesianCellGrid,
    _write_cell_vti,
)


def test_fixed_grid_connectivity_detects_detached_island(tmp_path: Path) -> None:
    topology_state = _write_topology_state(
        tmp_path / "contract",
        cell_shape=(5, 3, 1),
        solid_cells=[(0, 1, 0), (1, 1, 0), (2, 1, 0), (4, 1, 0)],
        root_cells=[(0, 1, 0)],
    )

    result = build_fixed_grid_connectivity_state(
        topology_state,
        min_connection_width_m=0.0,
        require_eroded_connectivity=False,
    )

    assert result.ok is False
    assert result.summary["status"] == "fail"
    assert result.summary["nominal"]["components"] == 2
    assert result.summary["nominal"]["unrooted_components"] == 1
    assert "nominal_unrooted_components" in result.summary["failure_reasons"]
    mesh = pv.read(result.connectivity_state_vti)
    violation = np.asarray(mesh.cell_data["connectivity_nominal_violation"])
    assert np.count_nonzero(violation) > 0


def test_fixed_grid_connectivity_eroded_check_rejects_thin_bridge(
    tmp_path: Path,
) -> None:
    solid_cells = [(0, 3, 0)]
    solid_cells.extend((x, 3, 0) for x in range(1, 5))
    solid_cells.extend(
        (x, y, 0)
        for x in range(5, 8)
        for y in range(1, 6)
    )
    topology_state = _write_topology_state(
        tmp_path / "contract",
        cell_shape=(8, 7, 1),
        solid_cells=solid_cells,
        root_cells=[(0, 3, 0)],
        spacing=(1.0, 1.0, 1.0),
    )

    result = build_fixed_grid_connectivity_state(
        topology_state,
        min_connection_width_m=2.2,
        require_eroded_connectivity=True,
    )

    assert result.ok is False
    assert result.summary["nominal"]["unrooted_components"] == 0
    assert result.summary["eroded"]["unrooted_components"] == 1
    assert "eroded_unrooted_components" in result.summary["failure_reasons"]
    mesh = pv.read(result.connectivity_state_vti)
    eroded_violation = np.asarray(mesh.cell_data["connectivity_eroded_violation"])
    assert np.count_nonzero(eroded_violation) > 0


def test_fixed_grid_connectivity_derivatives_match_central_difference(
    tmp_path: Path,
) -> None:
    topology_state = _write_topology_state(
        tmp_path / "contract",
        cell_shape=(4, 1, 1),
        solid_cells=[(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)],
        root_cells=[(0, 0, 0)],
        density_values={
            (1, 0, 0): 0.7,
            (2, 0, 0): 0.7,
            (3, 0, 0): 0.7,
        },
    )
    _, density_arrays = _read_test_density(topology_state)
    base_sensitivity = tmp_path / "base_sensitivity.vti"
    _write_base_sensitivity(
        topology_state,
        base_sensitivity,
        drag=np.arange(4, dtype=np.float32),
    )

    result = build_fixed_grid_connectivity_derivatives(
        topology_state,
        output_dir=tmp_path / "derivatives",
        base_sensitivity_vti=base_sensitivity,
        epsilon=1.0e-4,
        min_connection_width_m=0.0,
        require_eroded_connectivity=False,
    )

    assert result.ok is True
    assert result.optimizer_ready is True
    assert result.summary["method"]["derivative_status"] == (
        "finite_difference_reference_full"
    )
    mesh = pv.read(result.sensitivity_vti)
    sample_mask = np.asarray(mesh.cell_data["connectivity_derivative_sample_mask"])
    assert int(np.count_nonzero(sample_mask)) == 3
    assert np.allclose(np.asarray(mesh.cell_data["d_drag_d_rho"]), np.arange(4))

    cell_index = _cell_index((2, 0, 0), (4, 1, 1))
    epsilon = 1.0e-4
    plus = np.asarray(density_arrays["rho"], dtype=np.float64).copy()
    minus = plus.copy()
    plus[cell_index] += epsilon
    minus[cell_index] -= epsilon
    plus_objectives = evaluate_fixed_grid_connectivity_objectives(
        topology_state,
        density=plus,
        min_connection_width_m=0.0,
    )
    minus_objectives = evaluate_fixed_grid_connectivity_objectives(
        topology_state,
        density=minus,
        min_connection_width_m=0.0,
    )
    expected_nominal = (
        plus_objectives["connectivity_nominal_violation_l1"]
        - minus_objectives["connectivity_nominal_violation_l1"]
    ) / (2.0 * epsilon)
    expected_eroded = (
        plus_objectives["connectivity_eroded_violation_l1"]
        - minus_objectives["connectivity_eroded_violation_l1"]
    ) / (2.0 * epsilon)

    nominal = np.asarray(mesh.cell_data["d_connectivity_nominal_d_rho"])
    eroded = np.asarray(mesh.cell_data["d_connectivity_eroded_d_rho"])
    assert np.isclose(nominal[cell_index], expected_nominal, rtol=1.0e-5)
    assert np.isclose(eroded[cell_index], expected_eroded, rtol=1.0e-5)


def _write_topology_state(
    directory: Path,
    *,
    cell_shape: tuple[int, int, int],
    solid_cells: list[tuple[int, int, int]],
    root_cells: list[tuple[int, int, int]],
    spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
    density_values: dict[tuple[int, int, int], float] | None = None,
) -> Path:
    directory.mkdir(parents=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0),
        spacing=spacing,
        cell_shape=cell_shape,
    )
    count = grid.cell_count
    rho = np.zeros(count, dtype=np.float32)
    root_mask = np.zeros(count, dtype=np.uint8)
    for cell in solid_cells:
        rho[_cell_index(cell, cell_shape)] = 1.0
    for cell, value in (density_values or {}).items():
        rho[_cell_index(cell, cell_shape)] = float(value)
    for cell in root_cells:
        root_mask[_cell_index(cell, cell_shape)] = 1
        rho[_cell_index(cell, cell_shape)] = 1.0
    density_arrays = {
        "rho": rho,
        "rho_filtered": rho.copy(),
        "rho_projected": rho.copy(),
        "alpha": rho.copy(),
        "allowed_mask": np.ones(count, dtype=np.uint8),
        "forbidden_mask": np.zeros(count, dtype=np.uint8),
        "fixed_solid_mask": np.zeros(count, dtype=np.uint8),
        "root_mask": root_mask,
        "active_design_mask": np.ones(count, dtype=np.uint8),
    }
    _write_cell_vti(
        grid,
        density_arrays,
        directory / "density.vti",
        kind="fixed_grid_density",
    )
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


def _read_test_density(
    topology_state: Path,
) -> tuple[CartesianCellGrid, dict[str, np.ndarray]]:
    state = json.loads(topology_state.read_text(encoding="utf-8"))
    density_vti = topology_state.parent / str(state["density_vti"])
    mesh = pv.read(density_vti)
    grid = CartesianCellGrid(
        origin=tuple(float(value) for value in mesh.origin),
        spacing=tuple(float(value) for value in mesh.spacing),
        cell_shape=tuple(int(value) - 1 for value in mesh.dimensions),
    )
    arrays = {name: np.asarray(mesh.cell_data[name]) for name in mesh.cell_data}
    return grid, arrays


def _write_base_sensitivity(
    topology_state: Path,
    path: Path,
    *,
    drag: np.ndarray,
) -> None:
    grid, density_arrays = _read_test_density(topology_state)
    count = grid.cell_count
    active = np.asarray(density_arrays["active_design_mask"], dtype=np.uint8)
    _write_cell_vti(
        grid,
        {
            "d_downforce_d_rho": np.zeros(count, dtype=np.float32),
            "d_drag_d_rho": drag.astype(np.float32),
            "d_efficiency_constraint_d_rho": drag.astype(np.float32) * 3.0,
            "d_connectivity_nominal_d_rho": np.zeros(count, dtype=np.float32),
            "d_connectivity_eroded_d_rho": np.zeros(count, dtype=np.float32),
            "active_design_mask": active,
        },
        path,
        kind="fixed_grid_sensitivity",
    )


def _cell_index(cell: tuple[int, int, int], shape: tuple[int, int, int]) -> int:
    return int(np.ravel_multi_index(cell, shape, order="F"))
