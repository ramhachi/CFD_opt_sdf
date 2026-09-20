from __future__ import annotations

import hashlib
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

SOLVER_ID = "resp_rotated_force"


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


def _write_case(
    tmp_path: Path,
    *,
    solver_id: str = SOLVER_ID,
    converged: bool = True,
    primal_converged: bool = True,
    audit_only: bool = False,
    adjoint_residual_qualified: bool = True,
) -> Path:
    case = tmp_path / "case"
    root = case / "processor0"
    (root / "constant/polyMesh").mkdir(parents=True)
    (root / "constant/polyMesh/cellProcAddressing").write_text(_labels(list(range(6))), encoding="utf-8")
    (root / "1").mkdir()
    (root / f"1/topOSens{solver_id}").write_text(_field(f"topOSens{solver_id}", [1, 2, 3, 4, 5, 6]), encoding="utf-8")
    (root / "1/alphaTilda").write_text(_field("alphaTilda", [0.1] * 6), encoding="utf-8")
    (root / "1/beta").write_text(_field("beta", [0.9] * 6), encoding="utf-8")
    (root / "0").mkdir()
    (root / "0/alpha").write_text(_uniform_alpha(0.5), encoding="utf-8")
    log_text = (
        "DILUPBiCGStab:  Solving for Ux, Initial residual = 1e-7, "
        "Final residual = 1e-8, No Iterations 1\n"
    )
    if primal_converged:
        log_text += "op1 solution converged in 161 iterations\n"
    if converged:
        adjoint_residual = "1e-8" if adjoint_residual_qualified else "1e-3"
        log_text += (
            f"Adjoint solver {solver_id}\n"
            "DILUPBiCGStab:  Solving for Uax, Initial residual = 1e-7, "
            f"Final residual = {adjoint_residual}, No Iterations 1\n"
            f"{solver_id} solution converged in 713 iterations\n"
        )
    log_text += "\nEnd\n\nFinalising parallel run\n"
    (case / "log.adjointOptimisationFoam").write_text(log_text, encoding="utf-8")
    optimisation = case / "system" / "optimisationDict"
    optimisation.parent.mkdir()
    optimisation.write_text("qualified controls\n", encoding="utf-8")
    (case / "fixed_grid_primal_case_metadata.json").write_text(
        json.dumps(
            {
                "kind": "fixed_grid_primal_case",
                "case_dir": str(case.resolve()),
                "source_solver": {
                    "audit_only": audit_only,
                    "adjoint_iterations": 1 if audit_only else None,
                },
                "qualification_inputs": {
                    "optimisation_dict": {
                        "path": str(optimisation.resolve()),
                        "sha256": hashlib.sha256(optimisation.read_bytes()).hexdigest(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    metadata_path = case / "fixed_grid_primal_case_metadata.json"
    log_path = case / "log.adjointOptimisationFoam"
    solver_pass = converged and adjoint_residual_qualified
    (case / "fixed_grid_primal_summary.json").write_text(
        json.dumps(
            {
                "kind": "fixed_grid_primal_summary",
                "case_dir": str(case.resolve()),
                "status": "converged" if primal_converged and converged else "completed",
                "openfoam_run": {
                    "ok": True,
                    "returncode": 0,
                    "dry_run": False,
                    "timed_out": False,
                },
                "qualification_inputs": {
                    "case_metadata": {
                        "path": str(metadata_path.resolve()),
                        "sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
                    },
                    "optimisation_dict": {
                        "path": str(optimisation.resolve()),
                        "sha256": hashlib.sha256(optimisation.read_bytes()).hexdigest(),
                    },
                    "solver_log": {
                        "path": str(log_path.resolve()),
                        "sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                    },
                },
                "fixed_grid_convergence_qualification": {
                    "qualified": primal_converged and solver_pass,
                    "run_ok": True,
                    "solver_completed": True,
                    "solvers": {
                        "op1": {"qualified": primal_converged},
                        solver_id: {
                            "qualified": solver_pass,
                            "checks": [
                                {
                                    "field_pattern": "Ua.*",
                                    "threshold": 5e-7,
                                    "observed_max": 1e-8 if adjoint_residual_qualified else 1e-3,
                                    "status": "pass" if adjoint_residual_qualified else "fail",
                                }
                            ],
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
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


def _spec():
    return load_problem_spec(Path("examples/g2_openfoam_compile/project.yaml"))


def _verified_snapshot(tmp_path: Path):
    spec = _spec()
    grid = UniformCartesianCellGrid(
        origin=(-0.2, -0.1, -0.04),
        spacing=(0.02, 0.02, 0.02),
        cell_shape=(2, 3, 2),
    )
    masks = {mask_id: np.ones(grid.cell_count, dtype=np.uint8) for mask_id in CANONICAL_MASK_IDS}
    path = write_canonical_grid_snapshot(spec, grid=grid, masks=masks, path=tmp_path / "snapshot.json")
    return load_and_verify_canonical_grid_snapshot(path, spec)


def test_transfers_gradient_with_duality_and_records_provenance(tmp_path: Path) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)
    block_mesh = _write_block_mesh(tmp_path / "system/blockMeshDict")
    mapping = np.asarray([1, 0, 3, 2, 5, 4], dtype=np.int64)
    mapping_path = tmp_path / "source_global_cell_labels_by_xfastest.npy"
    np.save(mapping_path, mapping, allow_pickle=False)
    artifacts = reconstruct_and_write_canonical_gradient_transfer(
        case_dir=_write_case(tmp_path),
        adjoint_solver_id=SOLVER_ID,
        block_mesh_dict=block_mesh,
        verified_snapshot=snapshot,
        source_global_cell_labels_by_xfastest=mapping_path,
        output_directory=tmp_path / "canonical_result",
        response_id="rotated_force",
        problem_spec=spec,
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
    assert provenance["differentiated_response"]["problem_spec_response_id"] == "rotated_force"
    assert provenance["differentiated_response"]["openfoam_adjoint_solver_id"] == SOLVER_ID
    assert provenance["differentiated_response"]["adjoint_convergence"]["converged"] is True
    assert provenance["differentiated_response"]["adjoint_convergence"]["iterations"] == 713
    qualification = provenance["differentiated_response"]["case_qualification"]
    assert qualification["qualified"] is True
    assert qualification["primal"]["converged"] is True
    assert qualification["primal"]["iterations"] == 161
    assert qualification["case_metadata"]["audit_only"] is False
    assert qualification["final_field"]["time"] == "1"
    assert qualification["final_field"]["openfoam_field_name"] == f"topOSens{SOLVER_ID}"
    # Gate 0 (WP4/C1) semantic binding: direction, sign, and units are recorded.
    semantic = provenance["differentiated_response"]
    assert semantic["response_kind"] == "force"
    assert semantic["physical_direction_global"] == pytest.approx(
        [0.7071067811865476, 0.7071067811865476, 0.0], abs=1e-9
    )
    assert semantic["canonical_objective_sign"] == 1  # rotated_force is minimized
    assert {"objective_id": "multipoint_force", "sense": "minimize"} in semantic["referencing_objectives"]
    assert "coefficient" in semantic["value_units"]


def _mutated_spec(tmp_path: Path, *, mutation: str) -> Path:
    """Copy the g2 example spec and apply one semantic mutation (via yaml round-trip)."""

    import copy

    import yaml

    data = yaml.safe_load(Path("examples/g2_openfoam_compile/project.yaml").read_text(encoding="utf-8"))
    responses = {item["id"]: item for item in data["responses"]}
    if mutation == "kind_moment":
        responses["rotated_force"]["kind"] = "moment"
    elif mutation == "no_direction":
        del responses["rotated_force"]["direction"]
    elif mutation == "mixed_sense":
        data["objectives"].append(
            {
                "id": "also_rotated",
                "sense": "maximize",
                "terms": [{"coefficient": 1.0, "flow_case_id": "straight", "response_id": "rotated_force"}],
            }
        )
    elif mutation == "orphan_response":
        responses["rotated_force"]["options"] = dict(responses["rotated_force"].get("options") or {})
        responses["rotated_force"]["options"]["openfoam_adjoint_solver_id"] = "resp_orphan_force"
        for objective in data["objectives"]:
            objective["terms"] = [
                term for term in objective["terms"] if term.get("response_id") != "rotated_force"
            ]
        for constraint in data.get("constraints") or []:
            constraint["terms"] = [
                term for term in constraint["terms"] if term.get("response_id") != "rotated_force"
            ]
    else:
        raise AssertionError(mutation)
    path = tmp_path / "mutated_project.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _transfer_with_spec(tmp_path: Path, spec_path: Path, *, response_id: str = "rotated_force", solver_id: str = SOLVER_ID):
    spec = load_problem_spec(spec_path)
    grid = UniformCartesianCellGrid(
        origin=(-0.2, -0.1, -0.04),
        spacing=(0.02, 0.02, 0.02),
        cell_shape=(2, 3, 2),
    )
    masks = {mask_id: np.ones(grid.cell_count, dtype=np.uint8) for mask_id in CANONICAL_MASK_IDS}
    path = write_canonical_grid_snapshot(spec, grid=grid, masks=masks, path=tmp_path / "snapshot.json")
    snapshot = load_and_verify_canonical_grid_snapshot(path, spec)
    mapping = np.asarray([1, 0, 3, 2, 5, 4], dtype=np.int64)
    mapping_path = tmp_path / "mapping.npy"
    np.save(mapping_path, mapping, allow_pickle=False)
    return reconstruct_and_write_canonical_gradient_transfer(
        case_dir=_write_case(tmp_path, solver_id=solver_id),
        adjoint_solver_id=solver_id,
        block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
        verified_snapshot=snapshot,
        source_global_cell_labels_by_xfastest=mapping_path,
        output_directory=tmp_path / "canonical_result",
        response_id=response_id,
        problem_spec=spec,
    )


def test_rejects_non_force_response_kind(tmp_path: Path) -> None:
    spec_path = _mutated_spec(tmp_path, mutation="kind_moment")
    with pytest.raises(ValueError, match="kind='force'"):
        _transfer_with_spec(tmp_path, spec_path)


def test_rejects_response_without_direction(tmp_path: Path) -> None:
    spec_path = _mutated_spec(tmp_path, mutation="no_direction")
    with pytest.raises(ValueError, match="direction must contain exactly three finite numbers"):
        _transfer_with_spec(tmp_path, spec_path)


def test_rejects_mixed_objective_senses(tmp_path: Path) -> None:
    spec_path = _mutated_spec(tmp_path, mutation="mixed_sense")
    with pytest.raises(ValueError, match="mixed senses"):
        _transfer_with_spec(tmp_path, spec_path)


def test_rejects_response_with_no_declared_consumer(tmp_path: Path) -> None:
    spec_path = _mutated_spec(tmp_path, mutation="orphan_response")
    with pytest.raises(ValueError, match="no declared objective"):
        _transfer_with_spec(tmp_path, spec_path, solver_id="resp_orphan_force")


def test_rejects_response_bound_to_mismatched_adjoint_solver_id(tmp_path: Path) -> None:
    """A response must not accept a gradient differentiated by another response's solver.

    This is the C1 regression case named by the audit: the P0 closed loop
    declared response_id="drag" but transferred topOSensdownforce under it.
    Reproduced generically here using the two force responses already
    declared by examples/g2_openfoam_compile/project.yaml: a gradient
    reconstructed for "yaw_side_force"'s own solver must not bind to
    "rotated_force".
    """

    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)
    mismatched_solver_id = "resp_yaw_side_force"

    with pytest.raises(ValueError, match="is bound to OpenFOAM adjoint solver"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path, solver_id=mismatched_solver_id),
            adjoint_solver_id=mismatched_solver_id,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_unconverged_adjoint(tmp_path: Path) -> None:
    """C0: a finite, present topOSens from an unconverged adjoint is refused."""

    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)

    with pytest.raises(ValueError, match="did not report convergence"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path, converged=False),
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_converged_adjoint_over_unconverged_primal(tmp_path: Path) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)

    with pytest.raises(ValueError, match="Primal solver 'op1' did not report convergence"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path, primal_converged=False),
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_audit_only_case_even_when_primal_and_adjoint_converged(
    tmp_path: Path,
) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)

    with pytest.raises(ValueError, match="audit_only"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path, audit_only=True),
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_metadata_without_explicit_adjoint_iteration_policy(
    tmp_path: Path,
) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)
    case = _write_case(tmp_path)
    metadata_path = case / "fixed_grid_primal_case_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    del metadata["source_solver"]["adjoint_iterations"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="missing source_solver.adjoint_iterations"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=case,
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_case_when_optimisation_controls_changed_after_preparation(
    tmp_path: Path,
) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)
    case = _write_case(tmp_path)
    (case / "system" / "optimisationDict").write_text(
        "nIters 1; // mutated after metadata was written\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="optimisationDict hash does not match"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=case,
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_metadata_mutated_from_audit_only_to_qualified(tmp_path: Path) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)
    case = _write_case(tmp_path, audit_only=True)
    metadata_path = case / "fixed_grid_primal_case_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["source_solver"]["audit_only"] = False
    metadata["source_solver"]["adjoint_iterations"] = None
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="case_metadata hash does not match"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=case,
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_convergence_marker_when_final_adjoint_residual_fails(
    tmp_path: Path,
) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)

    with pytest.raises(ValueError, match="runtime convergence qualification did not pass"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path, adjoint_residual_qualified=False),
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_old_success_log_when_a_new_run_starts_after_summary(
    tmp_path: Path,
) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)
    case = _write_case(tmp_path)
    with (case / "log.adjointOptimisationFoam").open("a", encoding="utf-8") as handle:
        handle.write("\nTime = 2\nStarting a new run that never completed\n")

    with pytest.raises(ValueError, match="solver_log hash does not match"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=case,
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )
    assert not (tmp_path / "canonical_result").exists()


def test_rejects_missing_adjoint_log(tmp_path: Path) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)
    case_dir = _write_case(tmp_path)
    (case_dir / "log.adjointOptimisationFoam").unlink()

    with pytest.raises(ValueError, match="Adjoint convergence log not found"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=case_dir,
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )


def test_rejects_snapshot_mask_tamper_after_verification(tmp_path: Path) -> None:
    spec = _spec()
    snapshot = _verified_snapshot(tmp_path)
    artifact = snapshot.snapshot.path.parent / snapshot.snapshot.masks["root_mask"].relative_path
    values = np.load(artifact, allow_pickle=False)
    values[0] = 0
    np.save(artifact, values, allow_pickle=False)

    with pytest.raises(ValueError, match="mask hash mismatch during transfer: root_mask"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path),
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=snapshot,
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
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
    spec = _spec()
    with pytest.raises(ValueError, match=message):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path),
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict", x_upper=x_upper, nx=nx),
            verified_snapshot=_verified_snapshot(tmp_path),
            source_global_cell_labels_by_xfastest=_identity_mapping(tmp_path, 6),
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )


def test_rejects_invalid_source_cell_order_mapping(tmp_path: Path) -> None:
    spec = _spec()
    mapping = tmp_path / "bad_mapping.npy"
    np.save(mapping, np.asarray([0, 0, 2, 3, 4, 5], dtype=np.int64), allow_pickle=False)

    with pytest.raises(ValueError, match="must be a permutation"):
        reconstruct_and_write_canonical_gradient_transfer(
            case_dir=_write_case(tmp_path),
            adjoint_solver_id=SOLVER_ID,
            block_mesh_dict=_write_block_mesh(tmp_path / "system/blockMeshDict"),
            verified_snapshot=_verified_snapshot(tmp_path),
            source_global_cell_labels_by_xfastest=mapping,
            output_directory=tmp_path / "canonical_result",
            response_id="rotated_force",
            problem_spec=spec,
        )


def _identity_mapping(tmp_path: Path, count: int) -> Path:
    path = tmp_path / f"identity_mapping_{count}.npy"
    np.save(path, np.arange(count, dtype=np.int64), allow_pickle=False)
    return path
