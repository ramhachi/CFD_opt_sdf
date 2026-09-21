"""Tests for the preregistered density-to-SDF threshold sweep (DF4)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.extraction_sweep import ExtractionSweepError, run_extraction_threshold_sweep
from cfd_sdf.fixed_grid_contract import CartesianCellGrid, _write_cell_vti


def _write_state(
    directory: Path,
    *,
    cell_shape: tuple[int, int, int] = (6, 6, 6),
    solid_boxes: tuple = (((1, 4), (1, 4), (1, 4)),),
    all_zero: bool = False,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    grid = CartesianCellGrid(
        origin=(0.0, 0.0, 0.0),
        spacing=(1.0, 1.0, 1.0),
        cell_shape=cell_shape,
    )
    count = grid.cell_count
    density = np.zeros(count, dtype=np.float32)
    if not all_zero:
        for box in solid_boxes:
            for x in range(box[0][0], box[0][1] + 1):
                for y in range(box[1][0], box[1][1] + 1):
                    for z in range(box[2][0], box[2][1] + 1):
                        density[_cell_index((x, y, z), cell_shape)] = 1.0
    root = np.zeros(count, dtype=np.uint8)
    root[_cell_index((1, 3, 3), cell_shape)] = 1
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
    state = {
        "schema_version": 1,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "density_vti": "density.vti",
        "source_solver": {"backend": "test"},
    }
    path = directory / "topology_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def _cell_index(index: tuple[int, int, int], shape: tuple[int, int, int]) -> int:
    x, y, z = index
    return x + shape[0] * (y + shape[1] * z)


def test_sweep_records_all_thresholds_and_selects_inside_range(tmp_path: Path):
    state = _write_state(tmp_path / "candidate")
    summary = run_extraction_threshold_sweep(
        state,
        thresholds=[0.3, 0.5, 0.7],
        output_dir=tmp_path / "sweep",
        selection_rule={
            "kind": "registered_range_min_abs_volume_error",
            "range": [0.4, 0.6],
        },
    )
    assert len(summary["rows"]) == 3
    assert all(row["status"] == "ok" for row in summary["rows"])
    assert summary["selected_threshold"] == pytest.approx(0.5)
    assert "registered range" in summary["selection_reason"]
    assert summary["claims"]["selection_is_registered_not_observed_best"] is True
    assert (tmp_path / "sweep" / "sweep_summary.json").exists()
    for row in summary["rows"]:
        assert row["manifest_sha256"] is not None
        assert row["geometry_metrics_status"] in {"measured", "empty"}


def test_sweep_selects_first_passing_threshold_when_registered(tmp_path: Path):
    state = _write_state(tmp_path / "candidate")
    summary = run_extraction_threshold_sweep(
        state,
        thresholds=[0.3, 0.5, 0.7],
        output_dir=tmp_path / "sweep_first",
        selection_rule={
            "kind": "registered_range_first_that_passes",
            "range": [0.25, 0.75],
        },
    )
    assert summary["selected_threshold"] == pytest.approx(0.3)


def test_sweep_keeps_failed_threshold_rows(tmp_path: Path):
    state = _write_state(tmp_path / "empty_candidate", all_zero=True)
    summary = run_extraction_threshold_sweep(
        state,
        thresholds=[0.5],
        output_dir=tmp_path / "sweep_failed",
        selection_rule={
            "kind": "registered_range_min_abs_volume_error",
            "range": [0.4, 0.6],
        },
    )
    assert summary["rows"][0]["status"] == "error"
    assert summary["rows"][0]["error"]
    assert summary["selected_threshold"] is None
    assert "no eligible threshold" in summary["selection_reason"]


def test_sweep_rejects_unregistered_rules_and_bad_ranges(tmp_path: Path):
    state = _write_state(tmp_path / "candidate")
    with pytest.raises(ExtractionSweepError, match="unknown selection rule"):
        run_extraction_threshold_sweep(
            state,
            thresholds=[0.5],
            output_dir=tmp_path / "o1",
            selection_rule={"kind": "best_observed", "range": [0.4, 0.6]},
        )
    with pytest.raises(ExtractionSweepError, match="range"):
        run_extraction_threshold_sweep(
            state,
            thresholds=[0.5],
            output_dir=tmp_path / "o2",
            selection_rule={
                "kind": "registered_range_min_abs_volume_error",
                "range": [0.7, 0.3],
            },
        )
    with pytest.raises(ExtractionSweepError, match="thresholds must be inside"):
        run_extraction_threshold_sweep(
            state,
            thresholds=[1.5],
            output_dir=tmp_path / "o3",
            selection_rule={
                "kind": "registered_range_min_abs_volume_error",
                "range": [0.4, 0.6],
            },
        )
