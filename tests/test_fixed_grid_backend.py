from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv

import cfd_sdf.fixed_grid_backend as fixed_grid_backend
from cfd_sdf.fixed_grid_backend import (
    analyze_openfoam_topology_case,
    build_openfoam_capability_matrix,
    parse_merit_function,
    probe_openfoam_fixed_grid_backend,
)
from cfd_sdf.execution import run_openfoam_case
from cfd_sdf.porous_force_validation import (
    validate_efficiency_constraint_gradient,
    validate_porous_force_gradient,
)


def test_parse_merit_function_reads_objective_and_constraint(tmp_path: Path) -> None:
    merit = tmp_path / "meritFunction"
    merit.write_text(
        "# merit history\n"
        "1 1.0 1.0 (2)(0.50) 0 0\n"
        "2 0.8 0.8 (0.4)(-1.0e-4) 0 0\n",
        encoding="utf-8",
    )

    rows = parse_merit_function(merit)

    assert rows == [
        {"iteration": 1, "merit": 1.0, "objective": 1.0, "constraint": 0.5},
        {"iteration": 2, "merit": 0.8, "objective": 0.8, "constraint": -1.0e-4},
    ]


def test_analyze_openfoam_topology_case_requires_real_solver_completion(tmp_path: Path) -> None:
    case_dir = _write_completed_case(tmp_path / "case")

    analysis = analyze_openfoam_topology_case(case_dir)

    assert analysis["actual_solver_completed"] is True
    assert analysis["fixed_mesh_updates_observed"] is True
    assert analysis["brinkman_sensitivity_observed"] is True
    assert analysis["optimisation_iteration_count"] == 2
    assert analysis["objective_reduction"] == pytest.approx(0.2)
    assert analysis["has_alpha_tilda"] is True
    assert analysis["has_beta"] is True
    assert len(analysis["vtk_files"]) == 1

    (case_dir / "log.adjointOptimisationFoam").write_text(
        "mpirun has detected an attempt to run as root.\n",
        encoding="utf-8",
    )
    failed = analyze_openfoam_topology_case(case_dir)
    assert failed["actual_solver_completed"] is False
    assert failed["fixed_mesh_updates_observed"] is False
    assert failed["fatal_log_patterns"] == ["mpirun has detected an attempt to run as root"]


def test_probe_writes_partial_capability_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_dir = _write_completed_case(tmp_path / "case")
    environment = _environment_fixture()
    monkeypatch.setattr(
        fixed_grid_backend,
        "inspect_openfoam_topology_environment",
        lambda **_kwargs: environment,
    )

    artifacts = probe_openfoam_fixed_grid_backend(
        case_dir,
        output_dir=tmp_path / "report",
    )

    assert artifacts.environment_json.exists()
    assert artifacts.capability_matrix_json.exists()
    assert artifacts.summary_json.exists()
    assert artifacts.summary_markdown.exists()
    assert artifacts.summary["overall_status"] == "partial_pass_custom_force_objective_required"
    capabilities = build_openfoam_capability_matrix(environment, artifacts.summary["case_analysis"])
    assert capabilities["fixed_mesh_density_design_variable"]["status"] == "pass"
    assert capabilities["volume_topology_adjoint"]["status"] == "pass"
    assert capabilities["porous_body_directional_force_objective"]["status"] == "blocked_custom_objective_required"
    summary = json.loads(artifacts.summary_json.read_text(encoding="utf-8"))
    assert summary["next_required_action"].startswith("Implement and verify")


def test_capability_matrix_accepts_passing_porous_force_evidence(tmp_path: Path) -> None:
    case_analysis = analyze_openfoam_topology_case(_write_completed_case(tmp_path / "case"))
    capabilities = build_openfoam_capability_matrix(
        _environment_fixture(),
        case_analysis,
        {
            "status": "pass",
            "sign_match": True,
            "relative_error": 0.05,
        },
    )

    assert capabilities["porous_body_directional_force_objective"]["status"] == "pass"
    assert (
        capabilities["separate_downforce_drag_density_derivatives"]["status"]
        == "partial_single_direction_verified"
    )


def test_capability_matrix_closes_t0_with_strict_3d_force_evidence(tmp_path: Path) -> None:
    case_analysis = analyze_openfoam_topology_case(_write_completed_case(tmp_path / "case"))
    directional_pass = {
        "status": "pass",
        "sign_match": True,
        "relative_error": 0.05,
    }
    efficiency_pass = {
        **directional_pass,
        "separate_sensitivity_fields": True,
    }

    capabilities = build_openfoam_capability_matrix(
        _environment_fixture(),
        case_analysis,
        directional_pass,
        directional_pass,
        efficiency_pass,
    )

    assert capabilities["porous_body_directional_force_objective"]["status"] == "pass"
    assert capabilities["separate_downforce_drag_density_derivatives"]["status"] == "pass"
    assert capabilities["efficiency_constraint_density_derivative"]["status"] == "pass"
    assert fixed_grid_backend._overall_status(capabilities) == "pass_t0"
    assert fixed_grid_backend._next_required_action(capabilities).startswith("Proceed to T1")


def test_openfoam_runner_detects_swallowed_child_solver_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "Allrun").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (case_dir / "Allclean").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    def fake_run(command, *, cwd, stdout, stderr, text, timeout, check):
        assert command
        assert text is True
        assert check is False
        (Path(cwd) / "log.adjointOptimisationFoam").write_text(
            "mpirun has detected an attempt to run as root.\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("cfd_sdf.execution.subprocess.run", fake_run)

    result = run_openfoam_case(case_dir, backend="local", dry_run=False)

    assert result.returncode == 0
    assert result.ok is False
    assert result.error is not None
    assert result.solver_error_logs == [
        "log.adjointOptimisationFoam:mpirun has detected an attempt to run as root"
    ]


def test_validate_porous_force_gradient_writes_passing_report(tmp_path: Path) -> None:
    baseline = _write_force_validation_case(
        tmp_path / "baseline",
        objective=1.0,
        write_vtk=True,
    )
    plus = _write_force_validation_case(tmp_path / "plus", objective=1.0003)
    minus = _write_force_validation_case(tmp_path / "minus", objective=0.9997)

    result = validate_porous_force_gradient(
        baseline,
        plus,
        minus,
        output_dir=tmp_path / "report",
        epsilon=0.01,
        relative_error_tolerance=1.0e-8,
    )

    assert result.ok is True
    assert result.perturbed_cell_count == 1
    assert result.finite_difference_derivative == pytest.approx(0.03)
    assert result.adjoint_directional_derivative == pytest.approx(0.03)
    assert result.report_json.exists()
    assert result.report_markdown.exists()
    report = json.loads(result.report_json.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert report["brinkman_sensitivity_observed"] is True


def test_validate_efficiency_constraint_gradient_combines_fields(tmp_path: Path) -> None:
    baseline = _write_force_validation_case(
        tmp_path / "baseline",
        objective=1.0,
        write_vtk=True,
    )
    plus = _write_force_validation_case(tmp_path / "plus", objective=1.0003)
    minus = _write_force_validation_case(tmp_path / "minus", objective=0.9997)
    _write_objective(baseline, "downforce2dsolver", 0.2)
    _write_objective(plus, "downforce2dsolver", 0.2001)
    _write_objective(minus, "downforce2dsolver", 0.1999)

    result = validate_efficiency_constraint_gradient(
        baseline,
        plus,
        minus,
        output_dir=tmp_path / "report",
        efficiency_min=3.0,
        epsilon=0.01,
        relative_error_tolerance=1.0e-8,
    )

    assert result.ok is True
    assert result.finite_difference_derivative == pytest.approx(0.08)
    assert result.adjoint_directional_derivative == pytest.approx(0.08)
    assert result.separate_sensitivity_fields is True
    mesh = pv.read(result.sensitivity_vtk)
    assert "d_drag_d_alpha" in mesh.cell_data
    assert "d_downforce_d_alpha" in mesh.cell_data
    assert "d_efficiency_constraint_d_alpha" in mesh.cell_data


def _write_completed_case(case_dir: Path) -> Path:
    (case_dir / "optimisation" / "objective" / "0").mkdir(parents=True)
    (case_dir / "50").mkdir()
    (case_dir / "VTK" / "case_50").mkdir(parents=True)
    (case_dir / "openfoam_run_summary.json").write_text(
        json.dumps({"returncode": 0, "ok": True}),
        encoding="utf-8",
    )
    (case_dir / "log.adjointOptimisationFoam").write_text(
        "Setting design variables based on the alpha field\n"
        "Postprocessing Brinkman sensitivities for field U\n"
        "End\n\n"
        "Finalising parallel run\n",
        encoding="utf-8",
    )
    (case_dir / "optimisation" / "objective" / "0" / "meritFunction").write_text(
        "# merit history\n"
        "1 1.0 1.0 (2)(0.50) 0 0\n"
        "2 0.8 0.8 (0.4)(-1.0e-4) 0 0\n",
        encoding="utf-8",
    )
    (case_dir / "Allrun").write_text(
        "runApplication blockMesh\n"
        "runParallel $(getApplication)\n",
        encoding="utf-8",
    )
    (case_dir / "50" / "alphaTilda.gz").write_bytes(b"alpha")
    (case_dir / "50" / "beta.gz").write_bytes(b"beta")
    (case_dir / "VTK" / "case_50" / "internal.vtu").write_text(
        "<VTKFile/>\n",
        encoding="utf-8",
    )
    return case_dir


def _write_force_validation_case(
    case_dir: Path,
    *,
    objective: float,
    write_vtk: bool = False,
) -> Path:
    objective_dir = case_dir / "optimisation" / "objective" / "0"
    objective_dir.mkdir(parents=True)
    (objective_dir / "dragas1").write_text(
        f"# J JCycle\n1 {objective:.12g} {objective:.12g}\n",
        encoding="utf-8",
    )
    (case_dir / "log.adjointOptimisationFoam").write_text(
        "Creating objective function : drag of type porousDirectionalForce\n"
        "op1 solution converged in 10 iterations\n"
        "Postprocessing Brinkman sensitivities for field U\n"
        "End\n\n"
        "Finalising parallel run\n",
        encoding="utf-8",
    )
    if write_vtk:
        vtk_zero = case_dir / "VTK" / "case_0"
        vtk_one = case_dir / "VTK" / "case_1"
        vtk_zero.mkdir(parents=True)
        vtk_one.mkdir(parents=True)
        alpha_mesh = pv.ImageData(dimensions=(3, 2, 2)).cast_to_unstructured_grid()
        alpha_mesh.cell_data["alpha"] = np.array([0.5, 0.0])
        alpha_mesh.save(vtk_zero / "internal.vtu")
        sensitivity_mesh = pv.ImageData(dimensions=(3, 2, 2)).cast_to_unstructured_grid()
        sensitivity_mesh.cell_data["topOSensas1"] = np.array([0.03, -1.0])
        sensitivity_mesh.cell_data["topOSensdownforce2d"] = np.array([0.01, 0.5])
        sensitivity_mesh.save(vtk_one / "internal.vtu")
    return case_dir


def _write_objective(case_dir: Path, name: str, value: float) -> None:
    path = case_dir / "optimisation" / "objective" / "0" / name
    path.write_text(
        f"# J JCycle\n1 {value:.12g} {value:.12g}\n",
        encoding="utf-8",
    )


def _environment_fixture() -> dict[str, object]:
    return {
        "runtime_inspection": {"ok": True},
        "facts": {
            "topo_design_variables": "1",
            "topo_source": "1",
            "topo_sensitivity": "1",
            "mma_update": "1",
            "helmholtz_regularisation": "1",
            "turbulent_porosity_tutorial": "1",
            "force_objective": "1",
            "force_objective_patch_based": "1",
        },
    }
