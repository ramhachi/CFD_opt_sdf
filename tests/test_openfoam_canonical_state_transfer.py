from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.canonical_geometry_masks import CanonicalGeometryMaskArtifacts
from cfd_sdf.canonical_grid_snapshot import (
    CANONICAL_MASK_IDS,
    load_and_verify_canonical_grid_snapshot,
    write_canonical_grid_snapshot,
)
from cfd_sdf.fixed_grid_contract import CartesianCellGrid
from cfd_sdf.openfoam_blockmesh_grid import read_openfoam_blockmesh_uniform_cartesian_grid
from cfd_sdf.openfoam_canonical_state_transfer import write_openfoam_source_state_transfer
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid
from cfd_sdf.problem_spec import load_problem_spec
from cfd_sdf.stage_t_candidate_binding import VerifiedStageTCandidateBinding


def test_writes_conservative_source_rho_and_candidate_provenance(tmp_path: Path) -> None:
    verified, canonical_rho = _verified_candidate(tmp_path)
    block_mesh = _write_block_mesh(tmp_path / "system/blockMeshDict")
    source_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(block_mesh)
    mapping_values = np.asarray([1, 0, 3, 2, 5, 4], dtype=np.int64)
    mapping = _mapping(tmp_path, mapping_values)

    artifacts = write_openfoam_source_state_transfer(
        verified_candidate=verified,
        source_mesh=source_mesh,
        source_global_cell_labels_by_xfastest=mapping,
        output_directory=tmp_path / "source-state",
    )

    with np.load(artifacts.fields_npz, allow_pickle=False) as payload:
        source_rho_xfastest = payload["source_rho_xfastest"]
        source_rho_global = payload["source_rho_global_label"]
        assert payload["source_global_cell_labels_by_xfastest"].tolist() == (
            mapping_values.tolist()
        )
    expected_xfastest = np.asarray(
        [np.mean(canonical_rho[index : index + 2]) for index in range(0, 12, 2)]
    )
    assert source_rho_xfastest == pytest.approx(expected_xfastest)
    expected_global = np.empty_like(expected_xfastest)
    expected_global[mapping_values] = expected_xfastest
    assert source_rho_global == pytest.approx(expected_global)

    provenance = json.loads(artifacts.provenance_json.read_text(encoding="utf-8"))
    assert provenance["status"] == "capability_only"
    assert provenance["qualified"] is False
    assert provenance["candidate_binding"]["candidate_id"] == "candidate_0000"
    assert provenance["transfer"]["state_map"] == "source = P @ target"
    assert provenance["transfer"]["inverse_state_map"] == "refused_not_defined"
    assert provenance["transfer"]["coverage"] == "full source and target grid domains"
    assert provenance["solver_field_conversion"]["status"] == "not_performed"
    assert provenance["target"]["cell_shape"] == [2, 3, 2]
    assert provenance["source"]["cell_shape"] == [1, 3, 2]
    assert provenance["source"]["cell_order_mapping"]["identity"] is False
    assert provenance["artifact_file"]["sha256"] == hashlib.sha256(
        artifacts.fields_npz.read_bytes()
    ).hexdigest()


def test_rejects_invalid_density_and_existing_output(tmp_path: Path) -> None:
    verified, _ = _verified_candidate(tmp_path)
    invalid_arrays = dict(verified.density_arrays)
    invalid_arrays["rho"] = np.full(12, 1.01)
    invalid = VerifiedStageTCandidateBinding(
        path=verified.path,
        binding=verified.binding,
        problem_spec=verified.problem_spec,
        canonical_grid=verified.canonical_grid,
        geometry_manifest=verified.geometry_manifest,
        topology_state_path=verified.topology_state_path,
        density_vti_path=verified.density_vti_path,
        density_grid=verified.density_grid,
        density_arrays=invalid_arrays,
    )
    source_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(
        _write_block_mesh(tmp_path / "system/blockMeshDict")
    )
    mapping = _mapping(tmp_path, np.arange(6, dtype=np.int64))

    with pytest.raises(ValueError, match="0 <= rho <= 1"):
        write_openfoam_source_state_transfer(
            verified_candidate=invalid,
            source_mesh=source_mesh,
            source_global_cell_labels_by_xfastest=mapping,
            output_directory=tmp_path / "invalid-output",
        )
    assert not (tmp_path / "invalid-output").exists()

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        write_openfoam_source_state_transfer(
            verified_candidate=verified,
            source_mesh=source_mesh,
            source_global_cell_labels_by_xfastest=mapping,
            output_directory=existing,
        )


def test_rejects_partial_source_target_coverage(tmp_path: Path) -> None:
    verified, _ = _verified_candidate(tmp_path)
    source_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(
        _write_block_mesh(tmp_path / "system/blockMeshDict", x_upper=-0.15)
    )
    mapping = _mapping(tmp_path, np.arange(6, dtype=np.int64))

    with pytest.raises(ValueError, match="not fully covered"):
        write_openfoam_source_state_transfer(
            verified_candidate=verified,
            source_mesh=source_mesh,
            source_global_cell_labels_by_xfastest=mapping,
            output_directory=tmp_path / "partial-output",
        )
    assert not (tmp_path / "partial-output").exists()


def _verified_candidate(
    tmp_path: Path,
) -> tuple[VerifiedStageTCandidateBinding, np.ndarray]:
    spec = load_problem_spec(Path("examples/g2_openfoam_compile/project.yaml"))
    grid = UniformCartesianCellGrid(
        origin=(-0.2, -0.1, -0.04),
        spacing=(0.02, 0.02, 0.02),
        cell_shape=(2, 3, 2),
    )
    masks = {
        mask_id: np.ones(grid.cell_count, dtype=np.uint8)
        for mask_id in CANONICAL_MASK_IDS
    }
    snapshot_path = write_canonical_grid_snapshot(
        spec,
        grid=grid,
        masks=masks,
        path=tmp_path / "snapshot.json",
    )
    snapshot = load_and_verify_canonical_grid_snapshot(snapshot_path, spec)
    binding_path = tmp_path / "stage_t_candidate_binding.json"
    binding_path.write_text('{"kind":"test-binding"}', encoding="utf-8")
    density_path = tmp_path / "density.vti"
    density_path.write_text("test-density", encoding="utf-8")
    topology_path = tmp_path / "topology_state.json"
    topology_path.write_text("{}", encoding="utf-8")
    rho = np.asarray(
        [0.0, 1.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.0, 0.0, 0.0, 0.3, 0.9],
        dtype=np.float64,
    )
    binding = {
        "problem": {
            "problem_id": spec.problem_id,
            "problem_spec_sha256": snapshot.snapshot.problem_spec_sha256,
            "execution_ready": True,
        },
        "candidate": {
            "candidate_id": "candidate_0000",
            "parent_candidate_id": None,
            "iteration": 0,
        },
        "density": {"array": "rho", "sha256": "a" * 64},
    }
    geometry = CanonicalGeometryMaskArtifacts(
        snapshot_path=snapshot_path,
        geometry_manifest_path=tmp_path / "geometry-manifest.json",
        mask_true_counts={mask_id: grid.cell_count for mask_id in CANONICAL_MASK_IDS},
        grid_cell_count=grid.cell_count,
    )
    verified = VerifiedStageTCandidateBinding(
        path=binding_path,
        binding=binding,
        problem_spec=spec,
        canonical_grid=snapshot,
        geometry_manifest=geometry,
        topology_state_path=topology_path,
        density_vti_path=density_path,
        density_grid=CartesianCellGrid(
            origin=grid.origin,
            spacing=grid.spacing,
            cell_shape=grid.cell_shape,
        ),
        density_arrays={"rho": rho},
    )
    return verified, rho


def _write_block_mesh(path: Path, *, x_upper: float = -0.16) -> Path:
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
    hex (0 1 2 3 4 5 6 7) (1 3 2) simpleGrading (1 1 1)
);
edges
(
);
""",
        encoding="utf-8",
    )
    return path


def _mapping(tmp_path: Path, values: np.ndarray) -> Path:
    path = tmp_path / "source_global_cell_labels_by_xfastest.npy"
    np.save(path, values, allow_pickle=False)
    return path
