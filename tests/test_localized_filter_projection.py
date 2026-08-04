from __future__ import annotations

import hashlib

import numpy as np
import pytest

from cfd_sdf.localized_design_state_manifest import LocalizedDesignGrid
from cfd_sdf.localized_filter_projection import (
    LocalizedConeFilterConfig,
    LocalizedHeavisideProjectionConfig,
    LocalizedTopologySolidDetectionConfig,
    apply_localized_cone_filter,
    apply_localized_cone_filter_adjoint,
    apply_localized_heaviside_projection,
    localized_heaviside_projection_derivative,
    read_canonical_filter_config,
    read_canonical_projection_config,
    topology_solid_mask,
    write_canonical_filter_config,
    write_canonical_projection_config,
    write_localized_cone_filtered_npy,
)


def _grid(shape=(5, 4, 3)):
    return LocalizedDesignGrid(origin=(0.0, 0.0, 0.0), spacing=(0.002, 0.002, 0.002), cell_shape=shape)


def test_uniform_active_field_is_invariant_and_nonactive_is_exact_zero() -> None:
    grid = _grid()
    active = np.ones(grid.cell_count, dtype=np.bool_)
    active[[0, 7, 19]] = False
    rho = np.zeros(grid.cell_count, dtype=np.float64)
    rho[active] = 0.375
    filtered = apply_localized_cone_filter(rho, active, grid, z_slab_size=2)
    assert np.array_equal(filtered[~active], np.zeros(np.count_nonzero(~active)))
    assert np.allclose(filtered[active], rho[active], rtol=0.0, atol=1.0e-15)


def test_mask_boundary_and_isolated_active_cells_do_not_source_or_normalise() -> None:
    grid = _grid((3, 1, 1))
    active = np.array([True, False, True], dtype=np.bool_)
    rho = np.array([0.25, 0.0, 0.75], dtype=np.float64)
    filtered = apply_localized_cone_filter(rho, active, grid)
    assert np.array_equal(filtered, rho)
    # A non-active value is invalid even though it is a geometrical neighbour.
    rho[1] = 1.0
    with pytest.raises(ValueError, match="exactly zero outside"):
        apply_localized_cone_filter(rho, active, grid)


def test_fractional_values_and_nonactive_fixed_root_forbidden_are_preserved() -> None:
    grid = _grid((4, 1, 1))
    active = np.array([True, True, False, False], dtype=np.bool_)
    rho = np.array([0.125, 0.875, 0.0, 0.0], dtype=np.float64)
    result = apply_localized_cone_filter(rho, active, grid)
    assert result[0] > 0.125 and result[0] < 0.875
    assert result[1] < 0.875 and result[1] > 0.125
    assert np.array_equal(result[2:], np.zeros(2))


def test_filter_is_byte_identical_across_slab_sizes_and_memmap_output(tmp_path) -> None:
    grid = _grid((5, 4, 4))
    active = np.ones(grid.cell_count, dtype=np.bool_)
    active[::7] = False
    rho = np.zeros(grid.cell_count, dtype=np.float64)
    rho[active] = np.linspace(0.0, 1.0, np.count_nonzero(active), dtype=np.float64)
    direct = apply_localized_cone_filter(rho, active, grid, z_slab_size=1)
    other = apply_localized_cone_filter(rho, active, grid, z_slab_size=3)
    assert direct.tobytes() == other.tobytes()
    path_a = write_localized_cone_filtered_npy(rho, active, grid, output_path=tmp_path / "a.npy", z_slab_size=1)
    path_b = write_localized_cone_filtered_npy(rho, active, grid, output_path=tmp_path / "b.npy", z_slab_size=3)
    assert hashlib.sha256(path_a.read_bytes()).hexdigest() == hashlib.sha256(path_b.read_bytes()).hexdigest()


def test_filter_adjoint_obeys_inner_product_without_assuming_symmetry() -> None:
    grid = _grid((4, 3, 2))
    active = np.ones(grid.cell_count, dtype=np.bool_)
    active[[0, 4, 10]] = False
    rho = np.zeros(grid.cell_count, dtype=np.float64)
    gradient = np.zeros(grid.cell_count, dtype=np.float64)
    rho[active] = np.linspace(0.1, 0.9, np.count_nonzero(active))
    gradient[active] = np.linspace(-2.0, 1.0, np.count_nonzero(active))
    left = float(np.dot(apply_localized_cone_filter(rho, active, grid), gradient))
    right = float(np.dot(rho, apply_localized_cone_filter_adjoint(gradient, active, grid)))
    assert left == pytest.approx(right, abs=2.0e-15)


def test_filter_and_adjoint_refuse_output_aliasing_their_input(tmp_path) -> None:
    grid = _grid((2, 1, 1))
    active = np.array([True, True], dtype=np.bool_)
    rho = np.array([0.25, 0.75], dtype=np.float64)
    with pytest.raises(ValueError, match="must not share memory"):
        apply_localized_cone_filter(rho, active, grid, out=rho)
    with pytest.raises(ValueError, match="must not share memory"):
        apply_localized_cone_filter(rho, active, grid, out=rho.view())
    mapped_path = tmp_path / "rho.npy"
    np.save(mapped_path, rho)
    mapped = np.load(mapped_path, mmap_mode="r+")
    with pytest.raises(ValueError, match="must not share memory"):
        apply_localized_cone_filter(mapped, active, grid, out=mapped)
    gradient = np.array([-1.0, 2.0], dtype=np.float64)
    with pytest.raises(ValueError, match="must not share memory"):
        apply_localized_cone_filter_adjoint(gradient, active, grid, out=gradient)


def test_projection_formula_endpoints_eta_monotonicity_and_derivative() -> None:
    active = np.array([True, True, True, False], dtype=np.bool_)
    values = np.array([0.0, 0.5, 1.0, 0.0], dtype=np.float64)
    config = LocalizedHeavisideProjectionConfig(beta=2.0, eta=0.5)
    projected = apply_localized_heaviside_projection(values, active, config=config)
    assert projected[0] == pytest.approx(0.0)
    assert projected[1] == pytest.approx(0.5)
    assert projected[2] == pytest.approx(1.0)
    assert np.all(np.diff(projected[:3]) > 0.0)
    derivative = localized_heaviside_projection_derivative(values, active, config=config)
    epsilon = 1.0e-6
    plus = values.copy(); plus[1] += epsilon
    minus = values.copy(); minus[1] -= epsilon
    finite_difference = (apply_localized_heaviside_projection(plus, active, config=config)[1] - apply_localized_heaviside_projection(minus, active, config=config)[1]) / (2.0 * epsilon)
    assert derivative[1] == pytest.approx(finite_difference, rel=1.0e-9)
    assert derivative[3] == 0.0


def test_configs_hash_and_topology_threshold_are_canonical(tmp_path) -> None:
    filter_path = tmp_path / "filter_config.json"
    projection_path = tmp_path / "projection_config.json"
    filter_config = LocalizedConeFilterConfig()
    projection_config = LocalizedHeavisideProjectionConfig()
    assert write_canonical_filter_config(filter_path, filter_config) == hashlib.sha256(filter_path.read_bytes()).hexdigest()
    assert write_canonical_projection_config(projection_path, projection_config) == hashlib.sha256(projection_path.read_bytes()).hexdigest()
    assert read_canonical_filter_config(filter_path) == filter_config
    assert read_canonical_projection_config(projection_path) == projection_config
    active = np.array([True, True, False], dtype=np.bool_)
    values = np.array([0.499999, 0.5, 0.0], dtype=np.float64)
    assert np.array_equal(topology_solid_mask(values, active, config=LocalizedTopologySolidDetectionConfig()), [False, True, False])


@pytest.mark.parametrize(
    "values, active, message",
    [
        (np.array([np.nan], dtype=np.float64), np.array([True]), "finite values"),
        (np.array([1.1], dtype=np.float64), np.array([True]), "finite values"),
        (np.array([0.2], dtype=np.float64), np.array([False]), "exactly zero"),
    ],
)
def test_filter_and_projection_reject_invalid_values(values, active, message) -> None:
    grid = _grid((1, 1, 1))
    with pytest.raises(ValueError, match=message):
        apply_localized_cone_filter(values, active, grid)
    with pytest.raises(ValueError, match=message):
        apply_localized_heaviside_projection(values, active)
