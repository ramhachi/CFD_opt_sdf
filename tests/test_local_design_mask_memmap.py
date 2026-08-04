from __future__ import annotations

import numpy as np
import pytest

from cfd_sdf.local_design_mask_memmap import build_local_design_mask_memmaps
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid


def _grid() -> UniformCartesianCellGrid:
    return UniformCartesianCellGrid(origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), cell_shape=(3, 2, 2))


def _roles() -> dict[str, np.ndarray]:
    count = _grid().cell_count
    design = np.ones(count, dtype=bool)
    forbidden = np.zeros(count, dtype=bool)
    forbidden[[1, 4, 8]] = True
    fixed = np.zeros(count, dtype=bool)
    fixed[[4, 10]] = True
    root = np.zeros(count, dtype=bool)
    root[10] = True
    return {"design_domain": design, "forbidden_region": forbidden, "fixed_solid": fixed, "root": root}


def _read(artifacts):
    return {name: np.load(path, mmap_mode="r") for name, path in artifacts.paths.items()}


def test_z_chunk_callback_and_precomputed_role_masks_are_identical(tmp_path) -> None:
    roles = _roles()
    expected = build_local_design_mask_memmaps(_grid(), output_dir=tmp_path / "expected", role_masks=roles, z_chunk_size=2)

    def containment(points: np.ndarray):
        # The input points retain x-fastest order inside each slab.
        flat = ((points[:, 0] - 0.5) + 3 * ((points[:, 1] - 0.5) + 2 * (points[:, 2] - 0.5))).astype(int)
        return {name: values[flat] for name, values in roles.items()}

    actual = build_local_design_mask_memmaps(_grid(), output_dir=tmp_path / "actual", role_containment=containment, z_chunk_size=1)
    assert actual.true_counts == expected.true_counts
    for name, values in _read(expected).items():
        assert values.dtype == np.dtype(bool)
        assert values.ndim == 1
        assert np.array_equal(values, _read(actual)[name])


def test_fixed_precedence_and_root_containment_are_derived_exactly(tmp_path) -> None:
    artifacts = build_local_design_mask_memmaps(_grid(), output_dir=tmp_path / "masks", role_masks=_roles())
    masks = _read(artifacts)
    # Cell 4 is both forbidden and fixed: fixed wins for forbidden, and raw
    # forbidden still excludes it from the active design field.
    assert not masks["forbidden_mask"][4]
    assert masks["fixed_solid_mask"][4]
    assert not masks["active_design_mask"][4]
    assert not masks["active_design_mask"][1]
    assert np.all(~masks["root_mask"] | masks["fixed_solid_mask"])


def test_refuses_existing_output_and_never_overwrites_published_snapshot(tmp_path) -> None:
    output = tmp_path / "published"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("immutable", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_local_design_mask_memmaps(_grid(), output_dir=output, role_masks=_roles())
    assert sentinel.read_text(encoding="utf-8") == "immutable"


def test_rejects_invalid_roots_and_requested_empty_masks_before_publication(tmp_path) -> None:
    invalid = _roles()
    invalid["root"] = np.zeros(_grid().cell_count, dtype=bool)
    invalid["root"][0] = True
    with pytest.raises(ValueError, match="contained"):
        build_local_design_mask_memmaps(_grid(), output_dir=tmp_path / "bad_root", role_masks=invalid)
    assert not (tmp_path / "bad_root").exists()

    empty = {name: np.zeros(_grid().cell_count, dtype=bool) for name in _roles()}
    with pytest.raises(ValueError, match="active_design_mask is empty"):
        build_local_design_mask_memmaps(_grid(), output_dir=tmp_path / "empty", role_masks=empty)
    assert not (tmp_path / "empty").exists()

    with pytest.raises(ValueError, match="root_mask is empty"):
        build_local_design_mask_memmaps(_grid(), output_dir=tmp_path / "empty_root", role_masks=empty, require_active=False, require_root=True)
    assert not (tmp_path / "empty_root").exists()
