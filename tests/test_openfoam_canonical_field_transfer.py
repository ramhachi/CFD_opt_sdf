from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.canonical_grid_snapshot import (
    CANONICAL_MASK_IDS,
    load_and_verify_canonical_grid_snapshot,
    write_canonical_grid_snapshot,
)
from cfd_sdf.openfoam_blockmesh_grid import read_openfoam_blockmesh_uniform_cartesian_grid
from cfd_sdf.openfoam_canonical_field_transfer import (
    reconstruct_and_write_canonical_gradient_transfer,
)
from cfd_sdf.openfoam_grid_transfer import ExactCartesianOverlapTransfer, UniformCartesianCellGrid
from cfd_sdf.problem_spec import load_problem_spec


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
    (root / "1/topOSensresp_force").write_text(_field("topOSensresp_force", [1, 2, 3, 4, 5, 6]), encoding="utf-8")
    (root / "1/alphaTilda").write_text(_field("alphaTilda", [0.1] * 6), encoding="utf-8")
    (root / "1/beta").write_text(_field("beta", [0.9] * 6), encoding="utf-8")
    (root / "0").mkdir()
    (root / "0/alpha").write_text(_uniform_alpha(0.5), encoding="utf-8")
    return case


def _write_block_mesh(path: Path, *, x_upper: float = -0.16, nx: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""scale 1;
vertices
(
    (-0.2 -0.1 -0.04)
    ({x_upper} -0.1 -0.04)
    ({x_upper} -0.04 -0.04)
    (-0.2 -0.04 -0.04)
    (-0.2 -0.1 0)
    ({x_upper} -0.1 0)
    ({x_upper} -0.04 0)
    (-0.2 -0.04 0)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} 3 2) simpleGrading (1 1 1)
);
edges
(
);
""",
        encoding="utf-8",
    )
    return path


def _verified_snapshot(tmp_path: Path):
    spec = load_problem_spec(Path("examples/g2_openfoam_compile/project.yaml"))
    grid = UniformCartesianCellGrid(
        origin=(-0.2, -0.1, -0.04),
        spacing=(0.02, 0.02, 0.02),
        cell_shape=(2, 3, 2),
    )
    masks = {mask_id: np.ones(grid.cell_count, dtype=np.uint8) for mask_id in CANONICAL_MASK_IDS}
    path = write_canonical_grid_snapshot(spec, grid=grid, masks=masks, path=tmp_path / "snapshot.json")
    return load_and_verify_canonical_grid_snapshot(path, spec)


def test_transfers_gradient_with_duality_and_records_provenance(tmp_path: Path) -> None:
    snapshot = _verified_snapshot(tmp_path)
    block_mesh = _write_block_mesh(tmp_path / "system/blockMeshDict")
    mapping = np.asarray([1, 0, 3, 2, 5, 4], dtype=np.int64)
    mapping_path = tmp_path / "source_global_cell_labels_by_xfastest.npy"
    np.save(mapping_path, mapping, allow_pickle=False)
    artifacts = reconstruct_and_write_canonical_gradient_transfer(
        case_dir=_write_case(tmp_path),
        adjoint_solver_id="resp_force",
        block_mesh_dict=block_mesh,
        verified_snapshot=snapshot,
        source_global_cell_labels_by_xfastest=mapping_path,
        output_directory=tmp_path / "canonical_result",
        response_id="rotated_force",
    )

    with np.load(artifacts.fields_npz, allow_pickle=False) as payload:
        gradient = payload["top_o_sensitivity_gradient"]
        assert payload["canonical_cell_indices"].tolist() == list(range(12))
    assert gradient == pytest.approx(
        [1.0, 1.0, 0.5, 0.5, 2.0, 2.0, 1.5, 1.5, 3.0, 3.0, 2.5, 2.5]
    )

    source = read_openfoam_blockmesh_uniform_cartesian_grid(block_mesh).grid
    transfer = ExactCartesianOverlapTransfer.build(source_grid=source, target_grid=snapshot.snapshot.grid)
    direction = np.linspace(-0.7, 0.9, snapshot.snapshot.grid.cell_count)
    source_gradient_xfastest = np.arange(1.0, 7.0)[mapping]
    assert np.dot(source_gradient_xfastest, transfer.transfer_state_to_source(direction)) == pytest.approx(
        np.dot(gradient, direction)
    )

    provenance = json.loads(artifacts.provenance_json.read_text(encoding="utf-8"))
    assert provenance["target"]["grid_sha256"] == snapshot.snapshot.grid_sha256
    assert provenance["transfer"]["gradient_map"] == "target_gradient = P.T @ source_gradient"
    assert provenance["transfer"]["coverage"] == "full source and target grid domains"
    assert provenance["source"]["cell_order_mapping"]["identity"] is False
    assert provenance["source"]["cell_order_mapping"]["mapping"] == (
        "global_label = values[x_fastest_index]"
    )
    assert set(provenance["state_field_transfer"]) == {"alpha_tilda", "beta", "raw_alpha"}
    assert all(item["status"] == "refused_not_provided" for item in provenance["state_field_transfer"].values())
    assert len(provenance["source"]["field_value_sha256"]["raw_alpha"]["source_file_sha256"]) == 1


def test_rejects_snapshot_mask_tamper_after_verification(tmp_path: Path) -> None:
    snapshot = _verified_snapshot(tmp_path)
    artifact = snapshot.snapshot.path.parent / snapshot.snapshot.masks["root_mask"].relative_path
    values = np.load(artifact, allow_pickle=False)
    values[0] = 0
    np.save(artifact, values, allow_pickle=False)

    with pytest.raises(ValueError, match="mask hash mismatch during transfer: root_mask"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path),
            adjoint_solver_id="resp_force",
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
        )


@pytest.mark.parametrize(
    ("x_upper", "nx", "message"),
    [(-0.15, 1, "not fully covered"), (-0.16, 2, "cell_count does not match")],
)
def test_rejects_incomplete_coverage_and_source_cell_count_mismatch(
    tmp_path: Path,
    x_upper: float,
    nx: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path),
            adjoint_solver_id="resp_force",
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict", x_upper=x_upper, nx=nx),
            verified_snapshot=_verified_snapshot(tmp_path),
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
        )


def test_rejects_invalid_source_cell_order_mapping(tmp_path: Path) -> None:
    mapping = tmp_path / "bad_mapping.npy"
    np.save(mapping, np.asarray([0, 0, 2, 3, 4, 5], dtype=np.int64), allow_pickle=False)

    with pytest.raises(ValueError, match="must be a permutation"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path),
            adjoint_solver_id="resp_force",
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=_verified_snapshot(tmp_path),
            source_global_cell_labels_by_xfastest=mapping,
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
        )


def _identity_mapping(tmp_path: Path, count: int) -> Path:
    path = tmp_path / f"identity_mapping_{count}.npy"
    np.save(path, np.arange(count, dtype=np.int64), allow_pickle=False)
    return path
