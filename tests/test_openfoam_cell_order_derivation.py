from __future__ import annotations

import json
from pathlib import Path

import pytest

from cfd_sdf.openfoam_cell_order_derivation import (
    derive_and_write_openfoam_cell_order_mapping,
)
from cfd_sdf.openfoam_grid_transfer import load_openfoam_cell_order_mapping


def _write_block_mesh(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """scale 1;
vertices
(
    (0 0 0)
    (2 0 0)
    (2 1 0)
    (0 1 0)
    (0 0 1)
    (2 0 1)
    (2 1 1)
    (0 1 1)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) (2 1 1) simpleGrading (1 1 1)
);
edges
(
);
""",
        encoding="utf-8",
    )
    return path


def _field(values: list[float]) -> str:
    return (
        "internalField nonuniform List<scalar>\n"
        f"{len(values)}\n(\n" + "\n".join(str(value) for value in values) + "\n)\n;\n"
    )


def _write_centres(case_dir: Path, *, cx: list[float], cy: list[float], cz: list[float], time_name: str = "0") -> None:
    directory = case_dir / time_name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "Cx").write_text(_field(cx), encoding="utf-8")
    (directory / "Cy").write_text(_field(cy), encoding="utf-8")
    (directory / "Cz").write_text(_field(cz), encoding="utf-8")


def test_derives_non_identity_permutation_from_cell_centres(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    _write_block_mesh(tmp_path / "system/blockMeshDict")
    # Global label 0 sits at x-fastest index 1; global label 1 sits at index 0.
    _write_centres(case_dir, cx=[1.5, 0.5], cy=[0.5, 0.5], cz=[0.5, 0.5])

    artifacts = derive_and_write_openfoam_cell_order_mapping(
        case_dir,
        block_mesh_dict=tmp_path / "system/blockMeshDict",
        output_directory=tmp_path / "mapping",
        execute=False,
    )

    mapping = load_openfoam_cell_order_mapping(artifacts.mapping_npy, cell_count=2)
    assert mapping.global_cell_labels_by_xfastest.tolist() == [1, 0]
    assert mapping.to_dict()["identity"] is False

    provenance = json.loads(artifacts.provenance_json.read_text(encoding="utf-8"))
    assert provenance["execution"]["executed"] is False
    assert provenance["cell_count"] == 2


def test_rejects_centre_off_grid(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    _write_block_mesh(tmp_path / "system/blockMeshDict")
    _write_centres(case_dir, cx=[1.5, 0.7], cy=[0.5, 0.5], cz=[0.5, 0.5])

    with pytest.raises(ValueError, match="not within tolerance"):
        derive_and_write_openfoam_cell_order_mapping(
            case_dir,
            block_mesh_dict=tmp_path / "system/blockMeshDict",
            output_directory=tmp_path / "mapping",
            execute=False,
        )
    assert not (tmp_path / "mapping").exists()


def test_rejects_duplicate_cell_centre_mapping(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    _write_block_mesh(tmp_path / "system/blockMeshDict")
    # Both global labels measure the same physical cell centre.
    _write_centres(case_dir, cx=[0.5, 0.5], cy=[0.5, 0.5], cz=[0.5, 0.5])

    with pytest.raises(ValueError, match="not a permutation"):
        derive_and_write_openfoam_cell_order_mapping(
            case_dir,
            block_mesh_dict=tmp_path / "system/blockMeshDict",
            output_directory=tmp_path / "mapping",
            execute=False,
        )
    assert not (tmp_path / "mapping").exists()


def test_missing_centres_without_execute_is_refused(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    _write_block_mesh(tmp_path / "system/blockMeshDict")

    with pytest.raises(ValueError, match="writeCellCentres output is missing"):
        derive_and_write_openfoam_cell_order_mapping(
            case_dir,
            block_mesh_dict=tmp_path / "system/blockMeshDict",
            output_directory=tmp_path / "mapping",
            execute=False,
        )
