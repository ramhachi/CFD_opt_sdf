from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.canonical_grid_snapshot import (
    CANONICAL_GRID_SNAPSHOT_KIND,
    CANONICAL_MASK_IDS,
    load_and_verify_canonical_grid_snapshot,
    read_canonical_grid_snapshot,
    verify_canonical_grid_snapshot,
    write_canonical_grid_snapshot,
)
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid
from cfd_sdf.problem_spec import load_problem_spec


def _spec():
    return load_problem_spec(Path("examples/g2_openfoam_compile/project.yaml"))


def _grid() -> UniformCartesianCellGrid:
    return UniformCartesianCellGrid(
        origin=(-0.2, -0.1, -0.04),
        spacing=(0.02, 0.02, 0.02),
        cell_shape=(2, 3, 2),
    )


def _masks(count: int) -> dict[str, np.ndarray]:
    return {
        "active_design_mask": np.array([1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 0, 1], dtype=np.uint8)[:count],
        "forbidden_mask": np.array([0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0], dtype=np.uint8)[:count],
        "fixed_solid_mask": np.array([0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0], dtype=np.uint8)[:count],
        "root_mask": np.array([0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0], dtype=np.uint8)[:count],
    }


def test_snapshot_round_trip_binds_problem_grid_and_mask_artifacts(tmp_path: Path) -> None:
    spec = _spec()
    grid = _grid()
    path = write_canonical_grid_snapshot(
        spec,
        grid=grid,
        masks=_masks(grid.cell_count),
        path=tmp_path / "canonical_grid_snapshot.json",
    )

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["kind"] == CANONICAL_GRID_SNAPSHOT_KIND
    assert set(raw["masks"]) == set(CANONICAL_MASK_IDS)
    assert raw["grid"]["sha256"] == grid.sha256
    assert all(not Path(item["path"]).is_absolute() for item in raw["masks"].values())

    snapshot = read_canonical_grid_snapshot(path)
    verified = verify_canonical_grid_snapshot(snapshot, spec)
    loaded = load_and_verify_canonical_grid_snapshot(path, spec)
    assert verified.snapshot.grid == grid
    assert loaded.snapshot.problem_id == spec.problem_id
    for mask_id, expected in _masks(grid.cell_count).items():
        assert verified.masks[mask_id].dtype == np.dtype(np.uint8)
        assert verified.masks[mask_id].flags.writeable is False
        assert verified.masks[mask_id] == pytest.approx(expected)


def test_snapshot_tampered_mask_is_rejected_by_artifact_hash(tmp_path: Path) -> None:
    spec = _spec()
    grid = _grid()
    path = write_canonical_grid_snapshot(
        spec,
        grid=grid,
        masks=_masks(grid.cell_count),
        path=tmp_path / "snapshot.json",
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    artifact = path.parent / raw["masks"]["active_design_mask"]["path"]
    values = np.load(artifact, allow_pickle=False)
    values[0] = 0
    np.save(artifact, values, allow_pickle=False)

    with pytest.raises(ValueError, match="mask hash mismatch: active_design_mask"):
        load_and_verify_canonical_grid_snapshot(path, spec)


def test_snapshot_problem_spec_mismatch_is_rejected(tmp_path: Path) -> None:
    spec = _spec()
    grid = _grid()
    path = write_canonical_grid_snapshot(
        spec,
        grid=grid,
        masks=_masks(grid.cell_count),
        path=tmp_path / "snapshot.json",
    )

    with pytest.raises(ValueError, match="problem_id"):
        load_and_verify_canonical_grid_snapshot(path, replace(spec, problem_id="other_problem"))


def test_snapshot_mask_dtype_is_verified_even_when_tamper_hash_is_updated(tmp_path: Path) -> None:
    spec = _spec()
    grid = _grid()
    path = write_canonical_grid_snapshot(
        spec,
        grid=grid,
        masks=_masks(grid.cell_count),
        path=tmp_path / "snapshot.json",
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    artifact = path.parent / raw["masks"]["root_mask"]["path"]
    np.save(artifact, np.zeros(grid.cell_count, dtype=np.float64), allow_pickle=False)
    raw["masks"]["root_mask"]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="root_mask must have dtype uint8"):
        load_and_verify_canonical_grid_snapshot(path, spec)


def test_snapshot_writer_rejects_noncanonical_spacing_and_mask_shape(tmp_path: Path) -> None:
    spec = _spec()
    bad_grid = UniformCartesianCellGrid(
        origin=(0.0, 0.0, 0.0),
        spacing=(0.02, 0.03, 0.02),
        cell_shape=(1, 1, 1),
    )
    with pytest.raises(ValueError, match="spacing"):
        write_canonical_grid_snapshot(
            spec,
            grid=bad_grid,
            masks={mask_id: np.ones(1, dtype=np.uint8) for mask_id in CANONICAL_MASK_IDS},
            path=tmp_path / "bad_spacing.json",
        )

    grid = _grid()
    masks = _masks(grid.cell_count)
    masks["root_mask"] = np.ones(grid.cell_count - 1, dtype=np.uint8)
    with pytest.raises(ValueError, match="root_mask must have shape"):
        write_canonical_grid_snapshot(
            spec,
            grid=grid,
            masks=masks,
            path=tmp_path / "bad_mask.json",
        )
