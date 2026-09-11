from __future__ import annotations

from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from cfd_sdf.canonical_grid_snapshot import CANONICAL_MASK_IDS, write_canonical_grid_snapshot
from cfd_sdf.cli import app
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid
from cfd_sdf.problem_spec import load_problem_spec


runner = CliRunner()
PROBLEM_YAML = Path("examples/g2_openfoam_compile/project.yaml")


def _field(name: str, values: list[float]) -> str:
    return (
        "FoamFile\n{\n    class volScalarField;\n"
        f"    object {name};\n}}\n\n"
        "dimensions [0 0 0 0 0 0 0];\n"
        f"internalField nonuniform List<scalar> {len(values)}\n(\n"
        + "\n".join(str(value) for value in values)
        + "\n);\n"
    )


def _labels(values: list[int]) -> str:
    return (
        "FoamFile\n{\n    class labelList;\n    object cellProcAddressing;\n}\n\n"
        f"{len(values)}\n(\n" + "\n".join(str(value) for value in values) + "\n);\n"
    )


def _uniform_alpha(value: float) -> str:
    return (
        "FoamFile\n{\n    class volScalarField;\n    object alpha;\n}\n\n"
        "dimensions [0 0 0 0 0 0 0];\n"
        f"internalField uniform {value};\n"
    )


def _write_case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    root = case / "processor0"
    (root / "constant/polyMesh").mkdir(parents=True)
    (root / "constant/polyMesh/cellProcAddressing").write_text(_labels(list(range(6))), encoding="utf-8")
    (root / "1").mkdir()
    (root / "1/topOSensdownforce").write_text(_field("topOSensdownforce", [1, 2, 3, 4, 5, 6]), encoding="utf-8")
    (root / "1/alphaTilda").write_text(_field("alphaTilda", [0.1] * 6), encoding="utf-8")
    (root / "1/beta").write_text(_field("beta", [0.9] * 6), encoding="utf-8")
    (root / "0").mkdir()
    (root / "0/alpha").write_text(_uniform_alpha(0.5), encoding="utf-8")
    return case


def _write_block_mesh(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """scale 1;
vertices
(
    (-0.2 -0.1 -0.04)
    (-0.16 -0.1 -0.04)
    (-0.16 -0.04 -0.04)
    (-0.2 -0.04 -0.04)
    (-0.2 -0.1 0)
    (-0.16 -0.1 0)
    (-0.16 -0.04 0)
    (-0.2 -0.04 0)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) (1 3 2) simpleGrading (1 1 1)
);
edges
(
);
""",
        encoding="utf-8",
    )
    return path


def test_transfer_openfoam_gradient_to_canonical_writes_expected_artifacts(tmp_path: Path) -> None:
    spec = load_problem_spec(PROBLEM_YAML)
    grid = UniformCartesianCellGrid(
        origin=(-0.2, -0.1, -0.04), spacing=(0.02, 0.02, 0.02), cell_shape=(2, 3, 2)
    )
    masks = {mask_id: np.ones(grid.cell_count, dtype=np.uint8) for mask_id in CANONICAL_MASK_IDS}
    snapshot_path = write_canonical_grid_snapshot(spec, grid=grid, masks=masks, path=tmp_path / "snapshot.json")

    case_dir = _write_case(tmp_path)
    block_mesh = _write_block_mesh(tmp_path / "system/blockMeshDict")
    mapping_path = tmp_path / "source_global_cell_labels_by_xfastest.npy"
    np.save(mapping_path, np.asarray([1, 0, 3, 2, 5, 4], dtype=np.int64), allow_pickle=False)
    output_directory = tmp_path / "canonical_result"

    result = runner.invoke(
        app,
        [
            "transfer-openfoam-gradient-to-canonical",
            str(case_dir),
            "downforce",
            str(block_mesh),
            str(snapshot_path),
            str(PROBLEM_YAML),
            str(mapping_path),
            str(output_directory),
            "--response-id",
            "rotated_force",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output_directory / "canonical_gradient.npz").exists()
    assert (output_directory / "provenance.json").exists()
    normalized_output = "".join(result.output.split())
    assert str(output_directory / "canonical_gradient.npz").replace(" ", "") in normalized_output
    assert str(output_directory / "provenance.json").replace(" ", "") in normalized_output

    with np.load(output_directory / "canonical_gradient.npz", allow_pickle=False) as payload:
        assert payload["top_o_sensitivity_gradient"].shape == (grid.cell_count,)


def test_transfer_openfoam_gradient_to_canonical_refuses_undeclared_response(tmp_path: Path) -> None:
    spec = load_problem_spec(PROBLEM_YAML)
    grid = UniformCartesianCellGrid(
        origin=(-0.2, -0.1, -0.04), spacing=(0.02, 0.02, 0.02), cell_shape=(2, 3, 2)
    )
    masks = {mask_id: np.ones(grid.cell_count, dtype=np.uint8) for mask_id in CANONICAL_MASK_IDS}
    snapshot_path = write_canonical_grid_snapshot(spec, grid=grid, masks=masks, path=tmp_path / "snapshot.json")
    case_dir = _write_case(tmp_path)
    block_mesh = _write_block_mesh(tmp_path / "system/blockMeshDict")
    mapping_path = tmp_path / "source_global_cell_labels_by_xfastest.npy"
    np.save(mapping_path, np.asarray([1, 0, 3, 2, 5, 4], dtype=np.int64), allow_pickle=False)

    result = runner.invoke(
        app,
        [
            "transfer-openfoam-gradient-to-canonical",
            str(case_dir),
            "downforce",
            str(block_mesh),
            str(snapshot_path),
            str(PROBLEM_YAML),
            str(mapping_path),
            str(tmp_path / "canonical_result"),
            "--response-id",
            "downforce",
        ],
    )

    assert result.exit_code != 0
    assert not (tmp_path / "canonical_result").exists()
