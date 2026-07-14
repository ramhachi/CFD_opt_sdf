from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from cfd_sdf.localized_design_transfer import LocalizedDesignToCfdTransfer
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid


def _grid(*, origin, spacing, shape):
    return UniformCartesianCellGrid(origin=origin, spacing=spacing, cell_shape=shape)


def _nonaligned_transfer() -> LocalizedDesignToCfdTransfer:
    return LocalizedDesignToCfdTransfer.build(
        cfd_grid=_grid(origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), shape=(4, 2, 1)),
        design_grid=_grid(origin=(0.25, 0.25, 0.0), spacing=(0.5, 0.75, 0.5), shape=(4, 2, 2)),
    )


def test_non_aligned_local_box_has_complete_design_coverage_and_partial_cfd_rows() -> None:
    transfer = _nonaligned_transfer()

    assert transfer.diagnostics.design_cell_coverage_min == pytest.approx(1.0, abs=1.0e-12)
    assert transfer.diagnostics.design_cell_coverage_max == pytest.approx(1.0, abs=1.0e-12)
    # x coverage=(.75, 1, .25, 0), y coverage=(.75, .75), x-fastest flat order.
    assert transfer.diagnostics.cfd_row_coverage == pytest.approx(
        [0.5625, 0.75, 0.1875, 0.0, 0.5625, 0.75, 0.1875, 0.0]
    )
    assert transfer.diagnostics.cfd_partial_row_count == 6
    assert transfer.diagnostics.cfd_uncovered_row_count == 2

    # A constant local design perturbation produces exactly the supported CFD-volume fraction.
    result = transfer.apply_forward(np.ones(transfer.design_cell_count))
    assert result.dtype == np.float64
    assert result == pytest.approx(transfer.diagnostics.cfd_row_coverage)


def test_non_aligned_transfer_conserves_integrated_design_volume_and_is_chunk_invariant() -> None:
    transfer = _nonaligned_transfer()
    values = np.linspace(-0.4, 0.7, transfer.design_cell_count)

    full = transfer.apply_forward(values)
    chunked = transfer.apply_forward(values, target_z_chunk_size=1)
    assert chunked == pytest.approx(full)
    assert np.sum(full) * transfer._cfd.cell_volume == pytest.approx(
        np.sum(values) * transfer._design.cell_volume, abs=1.0e-12
    )


def test_euclidean_adjoint_identity_and_chunk_iterator() -> None:
    transfer = _nonaligned_transfer()
    design_direction = np.linspace(-0.5, 0.8, transfer.design_cell_count)
    cfd_gradient = np.linspace(-1.1, 0.9, transfer.cfd_cell_count)

    adjoint = transfer.apply_adjoint(cfd_gradient, target_z_chunk_size=1)
    assert np.dot(cfd_gradient, transfer.apply_forward(design_direction, target_z_chunk_size=1)) == pytest.approx(
        np.dot(adjoint, design_direction), abs=1.0e-12
    )

    chunks = list(transfer.iter_adjoint_design_chunks(cfd_gradient, target_z_chunk_size=1))
    reconstructed = np.empty((2, 2, 4), dtype=np.float64)
    for target_z, values in chunks:
        reconstructed[target_z] = values.reshape((target_z.stop - target_z.start, 2, 4))
    assert reconstructed.reshape(-1) == pytest.approx(adjoint)


def test_chunk_plan_is_bounded_and_rejects_insufficient_or_invalid_budget() -> None:
    transfer = _nonaligned_transfer()
    plan = transfer.plan_target_z_chunks(10_000)
    assert plan.target_z_chunk_size == 2
    assert plan.estimated_workspace_bytes_per_target_z > 0
    with pytest.raises(ValueError, match="too small"):
        transfer.plan_target_z_chunks(plan.estimated_workspace_bytes_per_target_z - 1)
    with pytest.raises(ValueError, match="positive integer"):
        transfer.plan_target_z_chunks(0)


def test_out_of_bounds_design_grid_is_refused() -> None:
    cfd = _grid(origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), shape=(2, 1, 1))
    design = _grid(origin=(-0.01, 0.0, 0.0), spacing=(0.5, 1.0, 1.0), shape=(2, 1, 1))
    with pytest.raises(ValueError, match="contained"):
        LocalizedDesignToCfdTransfer.build(cfd_grid=cfd, design_grid=design)


@dataclass
class _InvalidGrid:
    origin: object = (0.0, 0.0, 0.0)
    spacing: object = ((1.0, 1.0), 1.0, 1.0)
    cell_shape: object = (1, 1, 1)
    cell_order: str = "x-fastest"


def test_nonuniform_or_noncanonical_grid_contract_is_refused() -> None:
    valid = _grid(origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), shape=(1, 1, 1))
    with pytest.raises(ValueError, match="spacing"):
        LocalizedDesignToCfdTransfer.build(cfd_grid=valid, design_grid=_InvalidGrid())
    with pytest.raises(ValueError, match="cell_order"):
        LocalizedDesignToCfdTransfer.build(
            cfd_grid=valid,
            design_grid=_InvalidGrid(spacing=(1.0, 1.0, 1.0), cell_order="z-fastest"),
        )
