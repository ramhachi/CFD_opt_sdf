from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.openfoam_grid_transfer import (
    CANONICAL_CELL_ORDER,
    ExactCartesianOverlapTransfer,
    UniformCartesianCellGrid,
)


def _grid(*, origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), shape=(2, 1, 1)):
    return UniformCartesianCellGrid(origin=origin, spacing=spacing, cell_shape=shape)


def test_state_transfer_is_constant_preserving_and_volume_averaged() -> None:
    source = _grid(spacing=(1.0, 1.0, 1.0), shape=(2, 1, 1))
    target = _grid(spacing=(0.5, 0.5, 1.0), shape=(4, 2, 1))
    transfer = ExactCartesianOverlapTransfer.build(source_grid=source, target_grid=target)

    assert transfer.matrix.shape == (2, 8)
    assert np.allclose(transfer.transfer_state_to_source(np.full(8, 0.37)), 0.37)
    # x-fastest target order: cells (x=0,1; y=0,1) are the first source cell.
    target_state = np.arange(8, dtype=np.float64)
    assert transfer.transfer_state_to_source(target_state) == pytest.approx([2.5, 4.5])
    assert np.asarray(transfer.matrix.sum(axis=1)).reshape(-1) == pytest.approx([1.0, 1.0])


def test_gradient_transfer_preserves_the_discrete_directional_derivative() -> None:
    source = _grid(spacing=(1.0, 1.0, 1.0), shape=(2, 1, 1))
    target = _grid(spacing=(0.5, 0.5, 1.0), shape=(4, 2, 1))
    transfer = ExactCartesianOverlapTransfer.build(source_grid=source, target_grid=target)
    direction = np.array([0.2, -0.3, 0.5, 0.7, -0.1, 0.4, -0.8, 0.6])
    source_gradient = np.array([1.7, -2.3])

    target_gradient = transfer.transfer_gradient_to_target(source_gradient)
    assert np.dot(source_gradient, transfer.transfer_state_to_source(direction)) == pytest.approx(
        np.dot(target_gradient, direction)
    )
    assert target_gradient == pytest.approx(transfer.matrix.T @ source_gradient)


def test_active_domain_coverage_gap_is_rejected() -> None:
    source = _grid(shape=(2, 1, 1))
    # Covers [0, 1.5), so the second active source cell is only half-covered.
    target = _grid(spacing=(0.5, 1.0, 1.0), shape=(3, 1, 1))

    with pytest.raises(ValueError, match="source active domain is not fully covered"):
        ExactCartesianOverlapTransfer.build(source_grid=source, target_grid=target)


def test_active_masks_require_bidirectional_complete_coverage() -> None:
    source = _grid(shape=(2, 1, 1))
    target = _grid(shape=(2, 1, 1))
    source_mask = np.array([True, False])
    target_mask = np.array([True, True])

    with pytest.raises(ValueError, match="target active domain is not fully covered"):
        ExactCartesianOverlapTransfer.build(
            source_grid=source,
            target_grid=target,
            source_active_mask=source_mask,
            target_active_mask=target_mask,
        )


def test_grid_order_axes_shape_and_hash_are_validated() -> None:
    with pytest.raises(ValueError, match="cell_order"):
        UniformCartesianCellGrid(
            origin=(0.0, 0.0, 0.0),
            spacing=(1.0, 1.0, 1.0),
            cell_shape=(1, 1, 1),
            cell_order="z-fastest",
        )
    with pytest.raises(ValueError, match="non-axis-aligned"):
        UniformCartesianCellGrid(
            origin=(0.0, 0.0, 0.0),
            spacing=(1.0, 1.0, 1.0),
            cell_shape=(1, 1, 1),
            axes=((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        )
    with pytest.raises(ValueError, match="finite values"):
        _grid(spacing=(1.0, np.nan, 1.0))

    grid = _grid()
    assert grid.cell_order == CANONICAL_CELL_ORDER
    with pytest.raises(ValueError, match="does not match"):
        ExactCartesianOverlapTransfer.build(
            source_grid=grid,
            target_grid=grid,
            expected_source_grid_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        ExactCartesianOverlapTransfer.build(
            source_grid=grid,
            target_grid=grid,
            expected_target_grid_sha256="bad",
        )


@pytest.mark.parametrize(
    "values,name",
    [
        (np.ones((2, 1)), "target_state"),
        (np.array([1.0, np.inf]), "source_gradient"),
    ],
)
def test_state_gradient_shape_and_finiteness_are_fail_closed(values, name: str) -> None:
    grid = _grid()
    transfer = ExactCartesianOverlapTransfer.build(source_grid=grid, target_grid=grid)

    method = transfer.transfer_state_to_source if name == "target_state" else transfer.transfer_gradient_to_target
    with pytest.raises(ValueError, match=name):
        method(values)


def test_mask_shape_and_dtype_are_fail_closed() -> None:
    grid = _grid()
    with pytest.raises(ValueError, match="source_active_mask"):
        ExactCartesianOverlapTransfer.build(
            source_grid=grid,
            target_grid=grid,
            source_active_mask=np.array([1, 1], dtype=np.uint8),
        )
    with pytest.raises(ValueError, match="target_active_mask"):
        ExactCartesianOverlapTransfer.build(
            source_grid=grid,
            target_grid=grid,
            target_active_mask=np.array([[True, True]]),
        )
