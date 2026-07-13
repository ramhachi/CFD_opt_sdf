from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cfd_sdf.openfoam_blockmesh_grid import read_openfoam_blockmesh_uniform_cartesian_grid
from cfd_sdf.openfoam_grid_transfer import CANONICAL_CELL_ORDER


def test_reads_single_uniform_axis_aligned_hex_with_provenance(tmp_path: Path) -> None:
    path = tmp_path / "blockMeshDict"
    path.write_text(_block_mesh(), encoding="utf-8")

    result = read_openfoam_blockmesh_uniform_cartesian_grid(path)

    assert result.lower == pytest.approx((-0.5, -1.0, 0.25))
    assert result.spacing == pytest.approx((0.5, 1.0, 0.25))
    assert result.cell_shape == (2, 2, 2)
    assert result.grid.cell_order == CANONICAL_CELL_ORDER
    assert result.grid.flat_index(1, 1, 1) == 7
    assert result.block_mesh_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.to_dict()["grid_sha256"] == result.grid.sha256


@pytest.mark.parametrize(
    ("replacement", "value", "message"),
    [
        ("simpleGrading (1 1 1)", "simpleGrading (1 2 1)", "simpleGrading"),
        (
            "hex (0 1 2 3 4 5 6 7) (2 2 2) simpleGrading (1 1 1)",
            "hex (0 1 2 3 4 5 6 7) (2 2 2) simpleGrading (1 1 1)\n    hex (0 1 2 3 4 5 6 7) (2 2 2) simpleGrading (1 1 1)",
            "multi-block, non-hex, and graded",
        ),
        (
            "( 1.0  2.0 0.5)",
            "( 1.0  1.4 0.5)",
            "not axis-aligned Cartesian corners",
        ),
    ],
)
def test_refuses_graded_multi_block_and_non_axis_aligned_meshes(
    tmp_path: Path, replacement: str, value: str, message: str
) -> None:
    path = tmp_path / "blockMeshDict"
    path.write_text(_block_mesh().replace(replacement, value, 1), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        read_openfoam_blockmesh_uniform_cartesian_grid(path)


def test_reads_actual_compiled_g2_block_mesh_when_runtime_artifact_is_available() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "g2_openfoam_compile"
        / "runs"
        / "compiled_cases"
        / "flow_straight"
        / "system"
        / "blockMeshDict"
    )
    if not path.is_file():
        pytest.skip("local compiled G2 runtime artifact is not present")

    result = read_openfoam_blockmesh_uniform_cartesian_grid(path)

    assert result.lower == pytest.approx((-1.0, -0.8, -0.6))
    assert result.cell_shape == (32, 16, 16)
    assert result.spacing == pytest.approx((0.09375, 0.1, 0.075))
    assert result.grid.cell_order == "x-fastest"
    assert result.grid_sha256 == result.grid.sha256
    assert result.block_mesh_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def _block_mesh() -> str:
    return """FoamFile
{
    version 2.0;
    format ascii;
    class dictionary;
    object blockMeshDict;
}

scale 0.5;

vertices
(
    (-1.0 -2.0 0.5)
    ( 1.0 -2.0 0.5)
    ( 1.0  2.0 0.5)
    (-1.0  2.0 0.5)
    (-1.0 -2.0 1.5)
    ( 1.0 -2.0 1.5)
    ( 1.0  2.0 1.5)
    (-1.0  2.0 1.5)
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (2 2 2) simpleGrading (1 1 1)
);

edges
(
);
"""
