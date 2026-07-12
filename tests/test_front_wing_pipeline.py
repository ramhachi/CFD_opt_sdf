from __future__ import annotations

import csv
import json
import pytest
import time
from pathlib import Path

import numpy as np
import yaml

from cfd_sdf.adjoint import run_openfoam_adjoint_adapter
from cfd_sdf.adjoint_calibration import (
    run_adjoint_calibration_summary,
    run_adjoint_direction_check,
    run_paired_adjoint_direction_check,
)
from cfd_sdf.adjoint_topology import run_adjoint_topology_optimization
from cfd_sdf.config import load_project
from cfd_sdf.constraints import check_constraints
from cfd_sdf.cfd import evaluate_openfoam_case
from cfd_sdf.density_optimizer import DensityOptimizerControls, run_density_optimization, run_density_update_step_from_sensitivity
from cfd_sdf.execution import OpenFoamRunResult, run_openfoam_case
from cfd_sdf.export_vtk import export_vti, export_zero_surface
from cfd_sdf.gradient_check import run_finite_difference_gradient_check
from cfd_sdf.openfoam import generate_openfoam_case
from cfd_sdf.openfoam_sensitivity import export_openfoam_surface_sensitivity_to_csv
from cfd_sdf.optimization import run_parametric_optimization
from cfd_sdf.parametric import build_parametric_front_wing, default_parameters, mock_aero
from cfd_sdf.projection import project_surface_sensitivity_to_density, write_mock_surface_sensitivity_csv
from cfd_sdf.runner import classify_candidate, run_practical_optimization
from cfd_sdf.sample_geometry import write_front_wing_demo_geometry
from cfd_sdf.sensitivity import (
    read_density_update_vti,
    read_sensitivity_vti,
    read_vti_scalar_arrays,
    write_density_update_preview,
    write_mock_sensitivity_artifacts,
)
from cfd_sdf.sdf import build_fields
from cfd_sdf.topology import (
    TopologyControls,
    build_density_field,
    low_fidelity_topology_aero,
    run_topology_exploration,
)
from cfd_sdf.validation import validate_outputs


def test_demo_pipeline_exports_valid_outputs(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path, voxel_size_m=0.06)
    config = load_project(project_yaml)
    bundle = build_fields(config)
    report, derived = check_constraints(config, bundle)
    assert report.ok

    config.resolved_output_dir.mkdir(parents=True, exist_ok=True)
    (config.resolved_output_dir / "report.json").write_text(
        json.dumps(report.to_dict(), indent=2),
        encoding="utf-8",
    )
    export_vti(bundle, config.resolved_output_dir, derived)
    export_zero_surface(bundle, config.resolved_output_dir)

    result = validate_outputs(config, expect_ok=True)
    assert result.ok, result.to_dict()
    assert result.point_count > 0


def test_missing_roots_fail_connectivity(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path, include_roots=False)
    config = load_project(project_yaml)
    bundle = build_fields(config)
    report, _ = check_constraints(config, bundle)
    assert not report.ok
    assert report.nominal_unrooted_components >= 1


def test_forbidden_intersection_fails(tmp_path: Path) -> None:
    project_yaml = _write_project(
        tmp_path,
        forbidden_file="geometry/front_wing_initial.stl",
    )
    config = load_project(project_yaml)
    bundle = build_fields(config)
    report, _ = check_constraints(config, bundle)
    assert not report.ok
    assert report.forbidden_intersection_cells > 0


def test_openfoam_case_generation(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path, voxel_size_m=0.06)
    config = load_project(project_yaml)
    bundle = build_fields(config)
    case_dir = config.resolved_output_dir / "openfoam_front_wing"

    summary = generate_openfoam_case(config, bundle, case_dir)

    assert summary.stl_count >= 1
    assert (case_dir / "system" / "snappyHexMeshDict").exists()
    assert (case_dir / "system" / "controlDict").exists()
    assert (case_dir / "Allrun").exists()
    assert (case_dir / "postprocess_forces.py").exists()
    assert "forceCoeffs" in (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    assert "design_front_wing_initial" in json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))[
        "objective"
    ]["force_patches"]


def test_openfoam_force_coeff_postprocess(tmp_path: Path) -> None:
    force_dir = tmp_path / "case" / "postProcessing" / "forceCoeffs" / "0"
    force_dir.mkdir(parents=True)
    (force_dir / "forceCoeffs.dat").write_text(
        "# Time Cm Cd Cl Cl(f) Cl(r)\n"
        "0 0.0 0.12 -0.36 -0.20 -0.16\n"
        "1 0.0 0.10 -0.40 -0.22 -0.18\n",
        encoding="utf-8",
    )

    result = evaluate_openfoam_case(tmp_path / "case", efficiency_min=3.0)

    assert result.ok
    assert result.drag_coefficient == 0.10
    assert result.downforce_coefficient == 0.40
    assert result.efficiency == 4.0
    assert result.efficiency_constraint == pytest.approx(-0.10)


def test_openfoam_coefficient_dat_postprocess(tmp_path: Path) -> None:
    force_dir = tmp_path / "case" / "postProcessing" / "forceCoeffs" / "0"
    force_dir.mkdir(parents=True)
    (force_dir / "coefficient.dat").write_text(
        "# Force and moment coefficients\n"
        "# Time Cd Cd(f) Cd(r) Cl Cl(f) Cl(r)\n"
        "499 0.12 0.06 0.06 0.18 0.10 0.08\n"
        "500 0.10 0.05 0.05 -0.40 -0.22 -0.18\n",
        encoding="utf-8",
    )

    result = evaluate_openfoam_case(tmp_path / "case", efficiency_min=3.0)

    assert result.ok
    assert result.source.endswith("coefficient.dat")
    assert result.drag_coefficient == 0.10
    assert result.downforce_coefficient == 0.40


def test_openfoam_run_dry_run_writes_summary(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "Allrun").write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    (case_dir / "Allclean").write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")

    result = run_openfoam_case(case_dir, backend="local", dry_run=True)

    assert result.ok
    assert result.dry_run
    assert result.returncode is None
    assert result.summary_path.exists()
    assert result.stdout_log.exists()
    assert result.stderr_log.exists()
    assert result.command[-1] == "chmod +x Allrun Allclean && ./Allrun"


def test_openfoam_docker_dry_run_uses_bind_mount(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "Allrun").write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    (case_dir / "Allclean").write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")

    result = run_openfoam_case(case_dir, backend="docker", dry_run=True)

    assert result.ok
    assert result.backend == "docker"
    assert result.docker_image == "opencfd/openfoam-default:2512"
    assert "--entrypoint" in result.command
    assert any(item.startswith("type=bind,source=") and item.endswith(",target=/case") for item in result.command)


def test_parametric_front_wing_and_mock_aero() -> None:
    params = default_parameters()
    mesh = build_parametric_front_wing(params)
    aero = mock_aero(params, efficiency_min=3.0)

    assert not mesh.is_empty
    assert aero["drag_coefficient"] > 0
    assert aero["downforce_coefficient"] > 0
    assert "efficiency_constraint" in aero


def test_parametric_optimization_writes_run_database(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    run_dir = tmp_path / "optimization"

    summary = run_parametric_optimization(
        project_yaml,
        run_dir=run_dir,
        iterations=2,
        evaluator="mock",
        seed=7,
        voxel_size_m=0.12,
    )

    assert len(summary.candidates) == 2
    assert (run_dir / "optimization_summary.json").exists()
    assert (run_dir / "history.csv").exists()
    assert (run_dir / "best" / "candidate_result.json").exists()
    assert (run_dir / "candidate_0000" / "project.yaml").exists()
    assert (run_dir / "candidate_0000" / "geometry" / "front_wing_initial.stl").exists()
    assert summary.best_candidate.objective == min(candidate.objective for candidate in summary.candidates)
    for candidate in summary.candidates:
        assert candidate.constraint_records
        assert candidate.status in {"accepted", "rejected"}
        assert 0.0 <= candidate.front_downforce_ratio <= 1.0


def test_parametric_optimization_resume_reuses_existing_results(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    run_dir = tmp_path / "optimization"

    first = run_parametric_optimization(
        project_yaml,
        run_dir=run_dir,
        iterations=2,
        evaluator="mock",
        seed=11,
        voxel_size_m=0.12,
    )
    result_path = run_dir / "candidate_0000" / "candidate_result.json"
    mtime = result_path.stat().st_mtime_ns
    time.sleep(0.01)

    second = run_parametric_optimization(
        project_yaml,
        run_dir=run_dir,
        iterations=2,
        evaluator="mock",
        seed=11,
        voxel_size_m=0.12,
        resume=True,
    )

    assert result_path.stat().st_mtime_ns == mtime
    assert second.candidates[0].objective == first.candidates[0].objective


def test_front_downforce_ratio_can_be_enforced(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12, enforce_front_ratio=True)
    summary = run_parametric_optimization(
        project_yaml,
        run_dir=tmp_path / "optimization",
        iterations=1,
        evaluator="mock",
        seed=1,
        voxel_size_m=0.12,
    )

    candidate = summary.candidates[0]
    assert candidate.status == "rejected"
    assert "front_downforce_ratio_max" in candidate.rejection_reasons


def test_topology_density_field_and_exploration(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    config = load_project(project_yaml)
    bundle = build_fields(config)
    density = build_density_field(bundle, TopologyControls())

    assert density.shape == bundle.grid.shape
    assert (density >= 0.5).sum() > 0
    assert (density[bundle.arrays["allowed_phi"] > 0.0] == 0.0).all()
    aero = low_fidelity_topology_aero(density, bundle, config, TopologyControls())
    assert aero["drag_coefficient"] > 0
    assert aero["downforce_coefficient"] > 0
    assert aero["efficiency_constraint"] < 0

    summary = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=2,
        seed=3,
        voxel_size_m=0.12,
    )

    best_pool = [candidate for candidate in summary.candidates if candidate.status == "accepted"] or summary.candidates
    assert summary.evaluator == "low-fi"
    assert len(summary.candidates) == 2
    assert summary.best_candidate.objective == min(candidate.objective for candidate in best_pool)
    assert (tmp_path / "topology" / "topology_summary.json").exists()
    assert (tmp_path / "topology" / "topology_history.csv").exists()
    assert (tmp_path / "topology" / "best_topology" / "topology_result.json").exists()
    for candidate in summary.candidates:
        assert candidate.design_state_json.exists()
        design_state = json.loads(candidate.design_state_json.read_text(encoding="utf-8"))
        assert candidate.density_vti.exists()
        assert candidate.density_vti.name == "density.vti"
        assert (candidate.candidate_dir / "density_field.vti").exists()
        assert candidate.density_stl.exists()
        assert design_state["schema_version"] == 1
        assert design_state["kind"] == "density_design_state"
        assert design_state["design_variable"] == "density"
        assert design_state["density_array"] == "density"
        assert Path(design_state["density_vti"]).name == "density.vti"
        assert Path(design_state["derived_geometry"]).name == "front_wing_initial.stl"
        assert candidate.status in {"accepted", "rejected"}
        assert candidate.constraint_records
        assert candidate.downforce_coefficient > 0
        assert candidate.drag_coefficient > 0
        assert 0.0 <= candidate.front_downforce_ratio <= 1.0
        assert candidate.density_cell_count > 0


def test_topology_openfoam_dry_run_writes_case(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    run_dir = tmp_path / "topology"

    summary = run_topology_exploration(
        project_yaml,
        run_dir=run_dir,
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
        evaluator="openfoam-dry-run",
        backend="local",
    )

    candidate = summary.candidates[0]
    case_dir = candidate.candidate_dir / "runs" / "front_wing_demo" / "openfoam_front_wing"
    assert summary.evaluator == "openfoam-dry-run"
    assert candidate.status == "accepted"
    assert (case_dir / "openfoam_case_summary.json").exists()
    assert json.loads((case_dir / "openfoam_run_summary.json").read_text(encoding="utf-8"))["dry_run"]


def test_topology_openfoam_execute_uses_cfd_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_openfoam_case(
        case_dir: Path,
        *,
        backend: str = "auto",
        dry_run: bool = True,
        timeout_seconds: int | None = None,
        docker_image: str | None = None,
    ) -> OpenFoamRunResult:
        assert backend == "docker"
        assert not dry_run
        assert timeout_seconds == 123
        force_dir = case_dir / "postProcessing" / "forceCoeffs" / "0"
        force_dir.mkdir(parents=True)
        (force_dir / "coefficient.dat").write_text(
            "# Force and moment coefficients\n"
            "# Time Cd Cd(f) Cd(r) Cl Cl(f) Cl(r)\n"
            "500 0.10 0.05 0.05 -0.40 -0.25 -0.15\n",
            encoding="utf-8",
        )
        stdout_log = case_dir / "log.runOpenFOAM.stdout"
        stderr_log = case_dir / "log.runOpenFOAM.stderr"
        summary_path = case_dir / "openfoam_run_summary.json"
        stdout_log.write_text("fake ok\n", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        result = OpenFoamRunResult(
            case_dir=case_dir.resolve(),
            backend=backend,
            dry_run=False,
            command=["fake-openfoam"],
            returncode=0,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            summary_path=summary_path,
            docker_image=docker_image,
        )
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr("cfd_sdf.topology.run_openfoam_case", fake_run_openfoam_case)
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    summary = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
        evaluator="openfoam",
        backend="docker",
        timeout_seconds=123,
    )

    candidate = summary.candidates[0]
    assert summary.evaluator == "openfoam"
    assert candidate.status == "accepted"
    assert candidate.cfd_case_dir is not None
    assert candidate.cfd_run is not None
    assert candidate.cfd_run["ok"]
    assert candidate.cfd_summary is not None
    assert candidate.cfd_summary["ok"]
    assert candidate.cfd_error is None
    assert candidate.drag_coefficient == pytest.approx(0.10)
    assert candidate.downforce_coefficient == pytest.approx(0.40)
    assert candidate.front_downforce_coefficient == pytest.approx(0.25)
    assert candidate.rear_downforce_coefficient == pytest.approx(0.15)
    assert candidate.front_downforce_ratio == pytest.approx(0.625)
    assert candidate.efficiency_constraint == pytest.approx(-0.10)
    assert candidate.objective == pytest.approx(-0.40)
    assert (candidate.cfd_case_dir / "cfd_summary.json").exists()


def test_sensitivity_io_and_density_update_preview(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    summary = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    candidate = summary.candidates[0]

    artifacts = write_mock_sensitivity_artifacts(candidate.design_state_json)
    assert artifacts.sensitivity_vti.exists()
    assert artifacts.sensitivity_summary_json.exists()
    sensitivity_summary = json.loads(artifacts.sensitivity_summary_json.read_text(encoding="utf-8"))
    assert sensitivity_summary["schema_version"] == 1
    assert sensitivity_summary["kind"] == "density_sensitivity_summary"
    assert sensitivity_summary["backend"] == "mock-analytic"
    assert sensitivity_summary["failed_or_missing_arrays"] == []

    sensitivity_grid, sensitivity_arrays = read_sensitivity_vti(artifacts.sensitivity_vti)
    assert sensitivity_grid.shape
    for array_name in (
        "objective_density_sensitivity",
        "downforce_density_sensitivity",
        "drag_density_sensitivity",
        "constraint_sensitivity",
        "active_mask",
    ):
        assert array_name in sensitivity_arrays
        assert sensitivity_arrays[array_name].shape == sensitivity_grid.shape
    active = sensitivity_arrays["active_mask"] > 0
    assert active.sum() > 0
    assert sensitivity_arrays["objective_density_sensitivity"][active].min() < 0.0

    preview = write_density_update_preview(candidate.design_state_json, move_limit=0.04)
    assert preview.density_update_vti.exists()
    update_grid, update_arrays = read_density_update_vti(preview.density_update_vti)
    assert update_grid.shape == sensitivity_grid.shape
    for array_name in ("density_old", "density_new", "density_delta", "objective_density_sensitivity", "active_mask"):
        assert array_name in update_arrays
        assert update_arrays[array_name].shape == update_grid.shape
    assert update_arrays["density_new"].min() >= 0.0
    assert update_arrays["density_new"].max() <= 1.0
    assert np.abs(update_arrays["density_delta"]).max() <= 0.040001
    assert np.all(update_arrays["density_delta"][update_arrays["active_mask"] == 0] == 0.0)


def test_density_update_can_blend_constraint_sensitivity(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    summary = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    candidate = summary.candidates[0]
    artifacts = write_mock_sensitivity_artifacts(candidate.design_state_json, output_dir=tmp_path / "sensitivity")

    objective_only = run_density_update_step_from_sensitivity(
        candidate.design_state_json,
        step_dir=tmp_path / "objective_only",
        index=0,
        controls=DensityOptimizerControls(move_limit=0.03, smoothing_radius_cells=0.0),
        sensitivity_vti=artifacts.sensitivity_vti,
        sensitivity_summary_json=artifacts.sensitivity_summary_json,
    )
    constrained = run_density_update_step_from_sensitivity(
        candidate.design_state_json,
        step_dir=tmp_path / "constraint_blend",
        index=0,
        controls=DensityOptimizerControls(
            move_limit=0.03,
            smoothing_radius_cells=0.0,
            constraint_sensitivity_weight=2.0,
        ),
        sensitivity_vti=artifacts.sensitivity_vti,
        sensitivity_summary_json=artifacts.sensitivity_summary_json,
    )

    _, objective_arrays = read_density_update_vti(objective_only.density_update_vti)
    _, constrained_arrays = read_density_update_vti(constrained.density_update_vti)
    for array_name in (
        "base_objective_density_sensitivity",
        "raw_constraint_sensitivity",
        "effective_constraint_sensitivity",
        "combined_update_sensitivity",
    ):
        assert array_name in constrained_arrays
    assert np.allclose(
        constrained_arrays["objective_density_sensitivity"],
        constrained_arrays["combined_update_sensitivity"],
    )
    assert not np.allclose(
        constrained_arrays["base_objective_density_sensitivity"],
        constrained_arrays["combined_update_sensitivity"],
    )
    assert not np.allclose(
        objective_arrays["density_delta"],
        constrained_arrays["density_delta"],
    )
    assert constrained.controls["constraint_sensitivity_weight"] == pytest.approx(2.0)
    assert constrained.controls["effective_constraint_sensitivity_weight"] == pytest.approx(2.0)
    assert constrained.controls["constraint_sensitivity_blend_policy"]["mode"] == "active"


def test_density_optimizer_runner_writes_history_resume_and_best(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    run_dir = tmp_path / "density_optimization"
    controls = DensityOptimizerControls(
        move_limit=0.04,
        volume_fraction_max=0.50,
        smoothing_radius_cells=0.5,
        root_preserve_distance_m=0.12,
    )

    first = run_density_optimization(
        topology.candidates[0].design_state_json,
        run_dir=run_dir,
        iterations=2,
        controls=controls,
    )

    assert len(first.steps) == 2
    assert (run_dir / "density_optimization_summary.json").exists()
    assert (run_dir / "density_optimization_history.csv").exists()
    assert (run_dir / "best_design" / "design_state.json").exists()
    for step in first.steps:
        assert step.output_design_state_json.exists()
        assert step.sensitivity_vti.exists()
        assert step.sensitivity_summary_json.exists()
        assert step.density_update_vti.exists()
        assert step.density_vti.exists()
        assert step.density_stl.exists()
        assert step.status in {"accepted", "rejected"}
        assert step.constraint_records
        assert step.volume_fraction <= 0.500001
        assert abs(step.density_delta_min) <= 0.040001
        assert abs(step.density_delta_max) <= 0.040001

    _, update_arrays = read_density_update_vti(first.steps[0].density_update_vti)
    assert "thickness_proxy" in update_arrays
    assert "root_anchor_mask" in update_arrays

    result_path = run_dir / "density_step_0000" / "density_step_result.json"
    mtime = result_path.stat().st_mtime_ns
    time.sleep(0.01)
    second = run_density_optimization(
        topology.candidates[0].design_state_json,
        run_dir=run_dir,
        iterations=2,
        controls=controls,
        resume=True,
    )

    assert result_path.stat().st_mtime_ns == mtime
    assert second.steps[0].objective == first.steps[0].objective


def test_finite_difference_gradient_check_compares_mock_sensitivity(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    candidate = topology.candidates[0]
    sensitivity = write_mock_sensitivity_artifacts(candidate.design_state_json, output_dir=tmp_path / "sensitivity")

    summary = run_finite_difference_gradient_check(
        candidate.design_state_json,
        sensitivity_vti=sensitivity.sensitivity_vti,
        output_dir=tmp_path / "gradient_check",
        sample_count=8,
        epsilon=1.0e-4,
        tolerance=1.0e-2,
        seed=9,
    )

    assert summary.report_json.exists()
    assert summary.samples_csv.exists()
    assert summary.check_vti.exists()
    assert summary.sample_count == 8
    assert summary.ok_count == 8
    assert summary.sign_mismatch_count == 0
    assert summary.relative_error_count == 0
    assert summary.failed_perturbation_count == 0
    assert summary.max_relative_error is not None
    assert summary.max_relative_error < 1.0e-2
    assert {sample.method for sample in summary.samples} <= {"central", "forward", "backward"}
    assert all(sample.sign_match for sample in summary.samples)

    _, check_arrays = read_vti_scalar_arrays(summary.check_vti)
    assert int(check_arrays["sampled_mask"].sum()) == 8
    assert set(np.unique(check_arrays["classification_code"][check_arrays["sampled_mask"] > 0]).tolist()) == {1}


def test_openfoam_adjoint_adapter_writes_run_summary_and_sensitivity_contract(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    candidate = topology.candidates[0]

    result = run_openfoam_adjoint_adapter(
        candidate.design_state_json,
        adjoint_case_dir=tmp_path / "adjoint_case",
        solver_backend="docker",
        dry_run=True,
        mock_fallback=True,
    )

    assert result.backend_id == "openfoam-adjoint"
    assert result.solver_backend == "docker"
    assert result.dry_run
    assert result.ok
    assert result.summary_path.exists()
    assert result.adjoint_case_dir.exists()
    assert (result.adjoint_case_dir / "adjoint_adapter_config.json").exists()
    assert (result.adjoint_case_dir / "system" / "optimisationDict").exists()
    assert (result.adjoint_case_dir / "system" / "finite-area" / "faSchemes").exists()
    assert (result.adjoint_case_dir / "constant" / "adjointRASProperties").exists()
    assert (result.adjoint_case_dir / "0" / "Ua").exists()
    assert (result.adjoint_case_dir / "0" / "pa").exists()
    assert result.force_patches
    assert "system/optimisationDict" in result.generated_files
    assert result.preflight["case_files_ready"] is True
    assert result.preflight["mesh_ready"] is False
    assert result.sensitivity_vti is not None
    assert result.sensitivity_vti.exists()
    assert result.sensitivity_summary_json is not None
    assert result.sensitivity_summary_json.exists()
    assert result.conversion_mode == "mock-contract-fallback"
    assert "adjointOptimisationFoam -case /case" in result.command[-1]


def test_openfoam_adjoint_execute_preflight_blocks_unmeshed_case_without_mock_fallback(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    candidate = topology.candidates[0]

    result = run_openfoam_adjoint_adapter(
        candidate.design_state_json,
        adjoint_case_dir=tmp_path / "adjoint_execute_case",
        solver_backend="docker",
        dry_run=False,
        mock_fallback=True,
    )

    assert not result.ok
    assert result.error is not None
    assert "preflight failed" in result.error
    assert result.sensitivity_vti is None
    assert result.sensitivity_summary_json is None
    assert result.conversion_mode == "execution-failed-no-conversion"
    assert "constant/polyMesh/boundary" in result.preflight["blocking_issues"]


def test_openfoam_face_sensitivity_exports_normalized_surface_csv(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    poly = case_dir / "constant" / "polyMesh"
    time_dir = case_dir / "400"
    poly.mkdir(parents=True)
    time_dir.mkdir(parents=True)
    (poly / "boundary").write_text(
        """
FoamFile {}
1
(
    design_front_wing_initial
    {
        type            wall;
        nFaces          2;
        startFace       1;
    }
)
""",
        encoding="utf-8",
    )
    (poly / "points").write_text(
        """
FoamFile {}
4
(
(0 0 0)
(1 0 0)
(0 1 0)
(0 0 1)
)
""",
        encoding="utf-8",
    )
    (poly / "faces").write_text(
        """
FoamFile {}
3
(
3(0 1 2)
3(0 1 3)
3(0 2 3)
)
""",
        encoding="utf-8",
    )
    raw = time_dir / "faceSensNormalfaceBased-RMult_2"
    raw.write_text(
        """
FoamFile {}
dimensions      [0 0 0 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    design_front_wing_initial
    {
        type            calculated;
        value           nonuniform List<scalar>
2
(
1.5
-2.0
)
;
    }
}
""",
        encoding="utf-8",
    )

    exported = export_openfoam_surface_sensitivity_to_csv(
        case_dir=case_dir,
        sensitivity_file=raw,
        output_csv=tmp_path / "surface_sensitivity.csv",
        patches=["design_front_wing_initial"],
    )

    assert exported.point_count == 2
    assert exported.min_sensitivity == -2.0
    assert exported.max_sensitivity == 1.5
    assert exported.to_dict()["drag_sensitivity_mode"] == "zero-filled-not-provided-by-faceSensNormal"
    rows = list(csv.DictReader(exported.output_csv.open(encoding="utf-8")))
    assert len(rows) == 2
    assert rows[0]["objective_surface_sensitivity"] == "1.5"
    assert rows[0]["downforce_surface_sensitivity"] == "-1.5"
    assert rows[0]["drag_surface_sensitivity"] == "0"
    assert float(rows[0]["x"]) == pytest.approx(1 / 3)
    assert float(rows[0]["z"]) == pytest.approx(1 / 3)
    assert rows[1]["objective_surface_sensitivity"] == "-2"


def test_surface_sensitivity_projection_writes_density_sensitivity(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    candidate = topology.candidates[0]
    surface_csv = write_mock_surface_sensitivity_csv(
        candidate.design_state_json,
        output_csv=tmp_path / "surface_sensitivity.csv",
        max_points=250,
    )

    artifacts = project_surface_sensitivity_to_density(
        candidate.design_state_json,
        surface_csv,
        output_dir=tmp_path / "projected",
        smoothing_radius_cells=0.5,
    )

    assert artifacts.sensitivity_vti.exists()
    assert artifacts.sensitivity_summary_json.exists()
    assert artifacts.projection_diagnostics_vti.exists()
    summary = json.loads(artifacts.sensitivity_summary_json.read_text(encoding="utf-8"))
    assert summary["backend"] == "surface-projection"
    assert summary["projection_method"] == "kd-tree-gaussian-surface-to-density"
    assert summary["surface_point_count"] > 0
    assert summary["projected_active_cell_count"] > 0
    assert summary["constraint_sensitivity_status"] == "available"
    assert summary["constraint_sensitivity_diagnostics"]["has_independent_drag_sensitivity"] is True

    _, arrays = read_sensitivity_vti(artifacts.sensitivity_vti)
    active = arrays["active_mask"] > 0
    assert active.sum() > 0
    assert arrays["objective_density_sensitivity"][active].min() < 0.0
    assert arrays["downforce_density_sensitivity"][active].max() > 0.0

    preview = write_density_update_preview(
        candidate.design_state_json,
        sensitivity_vti=artifacts.sensitivity_vti,
        output_dir=tmp_path / "projected_update",
        move_limit=0.03,
    )
    assert preview.density_update_vti.exists()
    _, update_arrays = read_density_update_vti(preview.density_update_vti)
    assert np.abs(update_arrays["density_delta"]).max() <= 0.030001


def test_surface_projection_flags_zero_drag_constraint_sensitivity(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    candidate = topology.candidates[0]
    surface_csv = write_mock_surface_sensitivity_csv(
        candidate.design_state_json,
        output_csv=tmp_path / "surface_sensitivity.csv",
        max_points=250,
    )
    rows = list(csv.DictReader(surface_csv.open(encoding="utf-8")))
    zero_drag_csv = tmp_path / "surface_sensitivity_zero_drag.csv"
    with zero_drag_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            row["drag_surface_sensitivity"] = "0"
            writer.writerow(row)

    artifacts = project_surface_sensitivity_to_density(
        candidate.design_state_json,
        zero_drag_csv,
        output_dir=tmp_path / "projected_zero_drag",
        smoothing_radius_cells=0.5,
    )

    summary = json.loads(artifacts.sensitivity_summary_json.read_text(encoding="utf-8"))
    diagnostics = summary["constraint_sensitivity_diagnostics"]
    assert summary["constraint_sensitivity_status"] == "degenerate_zero_drag_sensitivity"
    assert diagnostics["usable_for_efficiency_constraint_update"] is False
    assert diagnostics["has_independent_drag_sensitivity"] is False
    assert diagnostics["constraint_collinear_with_objective"] is True
    assert diagnostics["objective_constraint_cosine_active"] == pytest.approx(1.0)

    guarded = run_density_update_step_from_sensitivity(
        candidate.design_state_json,
        step_dir=tmp_path / "guarded_constraint_blend",
        index=0,
        controls=DensityOptimizerControls(
            move_limit=0.03,
            smoothing_radius_cells=0.0,
            constraint_sensitivity_weight=2.0,
        ),
        sensitivity_vti=artifacts.sensitivity_vti,
        sensitivity_summary_json=artifacts.sensitivity_summary_json,
    )
    _, guarded_arrays = read_density_update_vti(guarded.density_update_vti)
    assert "raw_constraint_sensitivity" not in guarded_arrays
    assert guarded.controls["constraint_sensitivity_weight"] == pytest.approx(2.0)
    assert guarded.controls["effective_constraint_sensitivity_weight"] == pytest.approx(0.0)
    assert guarded.controls["constraint_sensitivity_blend_policy"]["mode"] == "disabled_unusable_constraint_sensitivity"


def test_adjoint_adapter_projects_surface_csv_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    candidate = topology.candidates[0]
    surface_csv = write_mock_surface_sensitivity_csv(
        candidate.design_state_json,
        output_csv=tmp_path / "raw_surface_sensitivity.csv",
        max_points=120,
    )
    monkeypatch.setattr("cfd_sdf.adjoint._collect_raw_sensitivity_outputs", lambda _case_dir: [surface_csv])

    result = run_openfoam_adjoint_adapter(
        candidate.design_state_json,
        adjoint_case_dir=tmp_path / "adjoint_projected",
        solver_backend="docker",
        dry_run=True,
        mock_fallback=True,
    )

    assert result.conversion_mode == "surface-csv-projection"
    assert result.sensitivity_vti is not None
    assert result.sensitivity_vti.exists()
    assert result.sensitivity_summary_json is not None
    summary = json.loads(result.sensitivity_summary_json.read_text(encoding="utf-8"))
    assert summary["backend"] == "surface-projection"


def test_adjoint_topology_loop_writes_history_resume_and_best(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    run_dir = tmp_path / "adjoint_topology"
    controls = DensityOptimizerControls(move_limit=0.03, volume_fraction_max=0.55)

    first = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=run_dir,
        iterations=2,
        backend="docker",
        density_controls=controls,
    )

    assert len(first.steps) == 2
    assert (run_dir / "adjoint_topology_summary.json").exists()
    assert (run_dir / "adjoint_topology_summary.md").exists()
    assert (run_dir / "adjoint_topology_history.csv").exists()
    assert (run_dir / "best_design" / "adjoint_topology_step_result.json").exists()
    for step in first.steps:
        assert step.adjoint_summary_json.exists()
        assert step.surface_sensitivity_csv.exists()
        assert step.sensitivity_vti.exists()
        assert step.sensitivity_summary_json.exists()
        assert step.density_step_result_json.exists()
        assert step.output_design_state_json.exists()
        assert step.status in {"accepted", "rejected"}

    result_path = run_dir / "adjoint_step_0000" / "adjoint_topology_step_result.json"
    mtime = result_path.stat().st_mtime_ns
    time.sleep(0.01)
    second = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=run_dir,
        iterations=2,
        backend="docker",
        density_controls=controls,
        resume=True,
    )

    assert result_path.stat().st_mtime_ns == mtime
    assert second.steps[0].objective == first.steps[0].objective


def test_adjoint_topology_execute_primal_writes_cfd_and_feeds_adjoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_openfoam_case(
        case_dir: Path,
        *,
        backend: str = "auto",
        dry_run: bool = True,
        timeout_seconds: int | None = None,
        docker_image: str | None = None,
    ) -> OpenFoamRunResult:
        poly = case_dir / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        (poly / "boundary").write_text("FoamFile {}\n0\n(\n)\n", encoding="utf-8")
        force_dir = case_dir / "postProcessing" / "forceCoeffs" / "0"
        force_dir.mkdir(parents=True, exist_ok=True)
        (force_dir / "coefficient.dat").write_text(
            "# Time Cd Cl Cl(f) Cl(r)\n"
            "1 0.20 -0.80 -0.50 -0.30\n",
            encoding="utf-8",
        )
        stdout_log = case_dir / "log.runOpenFOAM.stdout"
        stderr_log = case_dir / "log.runOpenFOAM.stderr"
        summary_path = case_dir / "openfoam_run_summary.json"
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        result = OpenFoamRunResult(
            case_dir=case_dir,
            backend=backend,
            dry_run=dry_run,
            command=["fake-openfoam"],
            returncode=0,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            summary_path=summary_path,
            docker_image=docker_image,
        )
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr("cfd_sdf.adjoint_topology.run_openfoam_case", fake_run_openfoam_case)
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )

    summary = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=tmp_path / "adjoint_topology_primal",
        iterations=1,
        backend="docker",
        primal_execute=True,
        adjoint_execute=False,
        density_controls=DensityOptimizerControls(move_limit=0.03),
    )

    step = summary.steps[0]
    assert step.primal_case_dir is not None
    assert (step.primal_case_dir / "cfd_summary.json").exists()
    assert step.primal_cfd_summary is not None
    assert step.primal_cfd_summary["downforce_coefficient"] == pytest.approx(0.8)
    assert step.primal_error is None
    adjoint_summary = json.loads(step.adjoint_summary_json.read_text(encoding="utf-8"))
    assert Path(adjoint_summary["primal_case_dir"]) == step.primal_case_dir
    assert adjoint_summary["preflight"]["mesh_ready"] is True


def test_adjoint_topology_post_update_primal_reranks_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_openfoam_case(
        case_dir: Path,
        *,
        backend: str = "auto",
        dry_run: bool = True,
        timeout_seconds: int | None = None,
        docker_image: str | None = None,
    ) -> OpenFoamRunResult:
        poly = case_dir / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        (poly / "boundary").write_text("FoamFile {}\n0\n(\n)\n", encoding="utf-8")
        if "post_update_primal" in str(case_dir):
            row = "1 0.20 -1.20 -0.60 -0.60\n"
        else:
            row = "1 0.20 -0.80 -0.50 -0.30\n"
        force_dir = case_dir / "postProcessing" / "forceCoeffs" / "0"
        force_dir.mkdir(parents=True, exist_ok=True)
        (force_dir / "coefficient.dat").write_text(
            "# Time Cd Cl Cl(f) Cl(r)\n" + row,
            encoding="utf-8",
        )
        stdout_log = case_dir / "log.runOpenFOAM.stdout"
        stderr_log = case_dir / "log.runOpenFOAM.stderr"
        summary_path = case_dir / "openfoam_run_summary.json"
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        result = OpenFoamRunResult(
            case_dir=case_dir,
            backend=backend,
            dry_run=dry_run,
            command=["fake-openfoam"],
            returncode=0,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            summary_path=summary_path,
            docker_image=docker_image,
        )
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr("cfd_sdf.adjoint_topology.run_openfoam_case", fake_run_openfoam_case)
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )

    summary = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=tmp_path / "adjoint_topology_post_update",
        iterations=1,
        backend="docker",
        primal_execute=True,
        post_update_primal_execute=True,
        density_controls=DensityOptimizerControls(move_limit=0.03),
    )

    step = summary.steps[0]
    assert step.objective_source == "post_update_primal_cfd"
    assert step.objective == pytest.approx(-1.2)
    assert step.status == "accepted"
    assert step.post_update_primal_case_dir is not None
    assert step.post_update_primal_cfd_summary is not None
    assert step.post_update_primal_cfd_summary["downforce_coefficient"] == pytest.approx(1.2)
    assert step.post_update_constraint_records is not None
    assert summary.best_step.objective == pytest.approx(-1.2)


def test_adjoint_direction_check_compares_predicted_and_realized_deltas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_openfoam_case(
        case_dir: Path,
        *,
        backend: str = "auto",
        dry_run: bool = True,
        timeout_seconds: int | None = None,
        docker_image: str | None = None,
    ) -> OpenFoamRunResult:
        poly = case_dir / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        (poly / "boundary").write_text("FoamFile {}\n0\n(\n)\n", encoding="utf-8")
        if "post_update_primal" in str(case_dir):
            row = "1 0.20 -1.20 -0.60 -0.60\n"
        else:
            row = "1 0.20 -0.80 -0.50 -0.30\n"
        force_dir = case_dir / "postProcessing" / "forceCoeffs" / "0"
        force_dir.mkdir(parents=True, exist_ok=True)
        (force_dir / "coefficient.dat").write_text(
            "# Time Cd Cl Cl(f) Cl(r)\n" + row,
            encoding="utf-8",
        )
        stdout_log = case_dir / "log.runOpenFOAM.stdout"
        stderr_log = case_dir / "log.runOpenFOAM.stderr"
        summary_path = case_dir / "openfoam_run_summary.json"
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        result = OpenFoamRunResult(
            case_dir=case_dir,
            backend=backend,
            dry_run=dry_run,
            command=["fake-openfoam"],
            returncode=0,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            summary_path=summary_path,
            docker_image=docker_image,
        )
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr("cfd_sdf.adjoint_topology.run_openfoam_case", fake_run_openfoam_case)
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    summary = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=tmp_path / "adjoint_topology_direction",
        iterations=1,
        backend="docker",
        primal_execute=True,
        post_update_primal_execute=True,
        density_controls=DensityOptimizerControls(move_limit=0.03),
    )

    check = run_adjoint_direction_check(
        summary.steps[0].step_dir / "adjoint_topology_step_result.json",
        output_dir=tmp_path / "direction_check",
    )

    assert check.report_json.exists()
    assert check.report_markdown.exists()
    assert check.diagnostics_vti.exists()
    assert check.objective_metric.actual_delta == pytest.approx(-0.4)
    assert check.objective_metric.predicted_delta < 0.0
    assert check.objective_metric.sign_match is True
    assert check.objective_metric.classification == "sign_match"
    _, arrays = read_vti_scalar_arrays(check.diagnostics_vti)
    assert "objective_direction_contribution" in arrays


def test_paired_adjoint_direction_check_recommends_better_primal_direction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_openfoam_case(
        case_dir: Path,
        *,
        backend: str = "auto",
        dry_run: bool = True,
        timeout_seconds: int | None = None,
        docker_image: str | None = None,
    ) -> OpenFoamRunResult:
        poly = case_dir / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        (poly / "boundary").write_text("FoamFile {}\n0\n(\n)\n", encoding="utf-8")
        case_text = str(case_dir)
        if "negative" in case_text:
            row = "1 0.20 -1.10 -0.55 -0.55\n"
        elif "post_update_primal" in case_text:
            row = "1 0.20 -0.70 -0.35 -0.35\n"
        else:
            row = "1 0.20 -0.80 -0.50 -0.30\n"
        force_dir = case_dir / "postProcessing" / "forceCoeffs" / "0"
        force_dir.mkdir(parents=True, exist_ok=True)
        (force_dir / "coefficient.dat").write_text(
            "# Time Cd Cl Cl(f) Cl(r)\n" + row,
            encoding="utf-8",
        )
        stdout_log = case_dir / "log.runOpenFOAM.stdout"
        stderr_log = case_dir / "log.runOpenFOAM.stderr"
        summary_path = case_dir / "openfoam_run_summary.json"
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        result = OpenFoamRunResult(
            case_dir=case_dir,
            backend=backend,
            dry_run=dry_run,
            command=["fake-openfoam"],
            returncode=0,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            summary_path=summary_path,
            docker_image=docker_image,
        )
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr("cfd_sdf.adjoint_topology.run_openfoam_case", fake_run_openfoam_case)
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    topology_summary = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=tmp_path / "adjoint_topology_paired",
        iterations=1,
        backend="docker",
        primal_execute=True,
        post_update_primal_execute=True,
        density_controls=DensityOptimizerControls(move_limit=0.03),
    )

    paired = run_paired_adjoint_direction_check(
        topology_summary.steps[0].step_dir / "adjoint_topology_step_result.json",
        output_dir=tmp_path / "paired_direction_check",
        execute_primal=True,
        backend="docker",
    )

    assert paired.report_json.exists()
    assert paired.report_markdown.exists()
    assert paired.recommended_direction == "negative"
    assert paired.recommended_density_delta_multiplier == pytest.approx(-1.0)
    by_name = {candidate.name: candidate for candidate in paired.candidates}
    assert by_name["positive"].cfd_source == "step_post_update_primal"
    assert by_name["positive"].actual_objective_delta == pytest.approx(0.1)
    assert by_name["negative"].cfd_source == "executed_primal"
    assert by_name["negative"].actual_objective_delta == pytest.approx(-0.3)
    assert by_name["negative"].design_state_json.exists()
    assert by_name["negative"].density_update_vti.exists()
    summary_json = json.loads(paired.report_json.read_text(encoding="utf-8"))
    assert summary_json["recommended_direction"] == "negative"
    assert "sensitivity_sign_decision" in summary_json

    centered = run_paired_adjoint_direction_check(
        topology_summary.steps[0].step_dir / "adjoint_topology_step_result.json",
        output_dir=tmp_path / "centered_paired_direction_check",
        execute_primal=True,
        backend="docker",
        centered=True,
        perturbation_scale=0.5,
    )
    centered_by_name = {candidate.name: candidate for candidate in centered.candidates}
    assert centered.baseline_primal_cfd_summary is not None
    assert centered.perturbation_scale == pytest.approx(0.5)
    assert centered_by_name["positive"].density_delta_l2 > 0.0
    assert centered_by_name["negative"].density_delta_l2 > 0.0
    assert centered_by_name["positive"].density_delta_l2 < by_name["positive"].density_delta_l2
    assert centered.recommended_direction == "negative"
    assert centered.sensitivity_sign_decision == "paired_direction_selected"
    assert centered.suggested_sensitivity_multiplier_for_gradient_descent == pytest.approx(-1.0)

    calibration = run_adjoint_calibration_summary(
        [paired.report_json, centered.report_json],
        output_dir=tmp_path / "adjoint_calibration_summary",
    )
    assert calibration.report_json.exists()
    assert calibration.report_markdown.exists()
    assert calibration.observation_count >= 2
    assert calibration.recommended_sensitivity_multiplier_for_gradient_descent == pytest.approx(-1.0)
    assert calibration.recommended_derivative_multiplier is not None

    calibrated_loop = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=tmp_path / "adjoint_topology_calibrated",
        iterations=1,
        backend="docker",
        density_controls=DensityOptimizerControls(move_limit=0.03),
        calibration_summary_json=calibration.report_json,
    )
    assert calibrated_loop.calibration_record_json is not None
    assert calibrated_loop.calibration_record_json.exists()
    assert calibrated_loop.sensitivity_update_multiplier == pytest.approx(-1.0)
    assert calibrated_loop.sensitivity_derivative_multiplier == pytest.approx(
        calibration.recommended_derivative_multiplier
    )
    calibrated_step = calibrated_loop.steps[0]
    controls = dict(calibrated_step.density_step["controls"])
    assert controls["sensitivity_update_multiplier"] == pytest.approx(-1.0)
    assert controls["sensitivity_derivative_multiplier"] == pytest.approx(
        calibration.recommended_derivative_multiplier
    )
    _, update_arrays = read_density_update_vti(Path(str(calibrated_step.density_step["density_update_vti"])))
    assert "raw_objective_density_sensitivity" in update_arrays
    assert "objective_derivative_sensitivity" in update_arrays
    np.testing.assert_allclose(
        update_arrays["objective_density_sensitivity"],
        -update_arrays["raw_objective_density_sensitivity"],
        rtol=1.0e-6,
        atol=1.0e-6,
    )
    np.testing.assert_allclose(
        update_arrays["objective_derivative_sensitivity"],
        update_arrays["raw_objective_density_sensitivity"] * calibration.recommended_derivative_multiplier,
        rtol=1.0e-6,
        atol=1.0e-6,
    )


def test_adjoint_topology_stop_on_rejection_prevents_next_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_openfoam_case(
        case_dir: Path,
        *,
        backend: str = "auto",
        dry_run: bool = True,
        timeout_seconds: int | None = None,
        docker_image: str | None = None,
    ) -> OpenFoamRunResult:
        poly = case_dir / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        (poly / "boundary").write_text("FoamFile {}\n0\n(\n)\n", encoding="utf-8")
        if "post_update_primal" in str(case_dir):
            row = "1 0.20 -0.10 -0.05 -0.05\n"
        else:
            row = "1 0.20 -0.80 -0.50 -0.30\n"
        force_dir = case_dir / "postProcessing" / "forceCoeffs" / "0"
        force_dir.mkdir(parents=True, exist_ok=True)
        (force_dir / "coefficient.dat").write_text(
            "# Time Cd Cl Cl(f) Cl(r)\n" + row,
            encoding="utf-8",
        )
        stdout_log = case_dir / "log.runOpenFOAM.stdout"
        stderr_log = case_dir / "log.runOpenFOAM.stderr"
        summary_path = case_dir / "openfoam_run_summary.json"
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        result = OpenFoamRunResult(
            case_dir=case_dir,
            backend=backend,
            dry_run=dry_run,
            command=["fake-openfoam"],
            returncode=0,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            summary_path=summary_path,
            docker_image=docker_image,
        )
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr("cfd_sdf.adjoint_topology.run_openfoam_case", fake_run_openfoam_case)
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    run_dir = tmp_path / "adjoint_topology_stop"

    summary = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=run_dir,
        iterations=3,
        backend="docker",
        primal_execute=True,
        post_update_primal_execute=True,
        stop_on_rejection=True,
        density_controls=DensityOptimizerControls(move_limit=0.03),
    )

    assert len(summary.steps) == 1
    assert summary.steps[0].status == "rejected"
    assert summary.steps[0].rejection_reasons == ["efficiency_constraint"]
    assert summary.stopped_reason == "step_0000_rejected:efficiency_constraint"
    assert summary.stopped_step_index == 0
    assert not (run_dir / "adjoint_step_0001").exists()
    summary_json = json.loads((run_dir / "adjoint_topology_summary.json").read_text(encoding="utf-8"))
    assert summary_json["iterations"] == 3
    assert summary_json["completed_iterations"] == 1
    assert summary_json["stopped_reason"] == "step_0000_rejected:efficiency_constraint"
    summary_markdown = (run_dir / "adjoint_topology_summary.md").read_text(encoding="utf-8")
    assert "| Completed iterations | 1 |" in summary_markdown
    assert "| Stopped reason | step_0000_rejected:efficiency_constraint |" in summary_markdown


def test_adjoint_topology_can_continue_on_constraint_improvement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_openfoam_case(
        case_dir: Path,
        *,
        backend: str = "auto",
        dry_run: bool = True,
        timeout_seconds: int | None = None,
        docker_image: str | None = None,
    ) -> OpenFoamRunResult:
        poly = case_dir / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        (poly / "boundary").write_text("FoamFile {}\n0\n(\n)\n", encoding="utf-8")
        case_text = str(case_dir)
        if "adjoint_step_0001" in case_text and "post_update_primal" in case_text:
            row = "1 0.20 -0.30 -0.15 -0.15\n"
        elif "adjoint_step_0001" in case_text:
            row = "1 0.20 -0.20 -0.10 -0.10\n"
        elif "post_update_primal" in case_text:
            row = "1 0.20 -0.20 -0.10 -0.10\n"
        else:
            row = "1 0.20 -0.10 -0.05 -0.05\n"
        force_dir = case_dir / "postProcessing" / "forceCoeffs" / "0"
        force_dir.mkdir(parents=True, exist_ok=True)
        (force_dir / "coefficient.dat").write_text(
            "# Time Cd Cl Cl(f) Cl(r)\n" + row,
            encoding="utf-8",
        )
        stdout_log = case_dir / "log.runOpenFOAM.stdout"
        stderr_log = case_dir / "log.runOpenFOAM.stderr"
        summary_path = case_dir / "openfoam_run_summary.json"
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        result = OpenFoamRunResult(
            case_dir=case_dir,
            backend=backend,
            dry_run=dry_run,
            command=["fake-openfoam"],
            returncode=0,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            summary_path=summary_path,
            docker_image=docker_image,
        )
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr("cfd_sdf.adjoint_topology.run_openfoam_case", fake_run_openfoam_case)
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    run_dir = tmp_path / "adjoint_topology_improving_infeasible"

    summary = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=run_dir,
        iterations=2,
        backend="docker",
        primal_execute=True,
        post_update_primal_execute=True,
        stop_on_rejection=True,
        continue_on_constraint_improvement=True,
        density_controls=DensityOptimizerControls(move_limit=0.03),
    )

    assert len(summary.steps) == 2
    assert summary.accepted_count == 0
    assert summary.stopped_reason is None
    assert summary.steps[0].status == "improving_infeasible"
    assert summary.steps[1].status == "improving_infeasible"
    assert summary.steps[0].constraint_violation_before == pytest.approx(0.5)
    assert summary.steps[0].constraint_violation_after == pytest.approx(0.4)
    assert summary.steps[1].constraint_violation_before == pytest.approx(0.4)
    assert summary.steps[1].constraint_violation_after == pytest.approx(0.3)
    assert summary.steps[0].continuation_reason is not None
    assert (run_dir / "adjoint_step_0001" / "adjoint_topology_step_result.json").exists()
    summary_json = json.loads((run_dir / "adjoint_topology_summary.json").read_text(encoding="utf-8"))
    assert summary_json["completed_iterations"] == 2
    assert summary_json["stopped_reason"] is None
    history = (run_dir / "adjoint_topology_history.csv").read_text(encoding="utf-8")
    assert "improving_infeasible" in history
    assert "constraint_violation_before" in history


def test_adjoint_topology_efficiency_min_override_can_accept_real_cfd_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_openfoam_case(
        case_dir: Path,
        *,
        backend: str = "auto",
        dry_run: bool = True,
        timeout_seconds: int | None = None,
        docker_image: str | None = None,
    ) -> OpenFoamRunResult:
        poly = case_dir / "constant" / "polyMesh"
        poly.mkdir(parents=True, exist_ok=True)
        (poly / "boundary").write_text("FoamFile {}\n0\n(\n)\n", encoding="utf-8")
        row = "1 0.20 -0.25 -0.15 -0.10\n" if "post_update_primal" in str(case_dir) else "1 0.20 -0.20 -0.10 -0.10\n"
        force_dir = case_dir / "postProcessing" / "forceCoeffs" / "0"
        force_dir.mkdir(parents=True, exist_ok=True)
        (force_dir / "coefficient.dat").write_text(
            "# Time Cd Cl Cl(f) Cl(r)\n" + row,
            encoding="utf-8",
        )
        stdout_log = case_dir / "log.runOpenFOAM.stdout"
        stderr_log = case_dir / "log.runOpenFOAM.stderr"
        summary_path = case_dir / "openfoam_run_summary.json"
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
        result = OpenFoamRunResult(
            case_dir=case_dir,
            backend=backend,
            dry_run=dry_run,
            command=["fake-openfoam"],
            returncode=0,
            stdout_log=stdout_log,
            stderr_log=stderr_log,
            summary_path=summary_path,
            docker_image=docker_image,
        )
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        return result

    monkeypatch.setattr("cfd_sdf.adjoint_topology.run_openfoam_case", fake_run_openfoam_case)
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )
    run_dir = tmp_path / "adjoint_topology_efficiency_override"

    summary = run_adjoint_topology_optimization(
        topology.candidates[0].design_state_json,
        run_dir=run_dir,
        iterations=1,
        backend="docker",
        primal_execute=True,
        post_update_primal_execute=True,
        stop_on_rejection=True,
        density_controls=DensityOptimizerControls(move_limit=0.03),
        efficiency_min_override=0.9,
    )

    assert len(summary.steps) == 1
    assert summary.accepted_count == 1
    assert summary.steps[0].status == "accepted"
    assert summary.steps[0].constraints_ok
    assert summary.steps[0].post_update_primal_cfd_summary is not None
    assert summary.steps[0].post_update_primal_cfd_summary["efficiency_constraint"] == pytest.approx(-0.07)
    summary_json = json.loads((run_dir / "adjoint_topology_summary.json").read_text(encoding="utf-8"))
    assert summary_json["efficiency_min_override"] == pytest.approx(0.9)
    summary_markdown = (run_dir / "adjoint_topology_summary.md").read_text(encoding="utf-8")
    assert "| Efficiency min override | 0.9 |" in summary_markdown


def test_adjoint_topology_execute_failure_does_not_fall_back_to_mock(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    topology = run_topology_exploration(
        project_yaml,
        run_dir=tmp_path / "topology",
        iterations=1,
        seed=3,
        voxel_size_m=0.12,
    )

    with pytest.raises(RuntimeError, match="Adjoint execution failed"):
        run_adjoint_topology_optimization(
            topology.candidates[0].design_state_json,
            run_dir=tmp_path / "adjoint_topology_execute",
            iterations=1,
            backend="docker",
            adjoint_execute=True,
            density_controls=DensityOptimizerControls(move_limit=0.03),
        )

    adjoint_summary = (
        tmp_path
        / "adjoint_topology_execute"
        / "adjoint_step_0000"
        / "adjoint"
        / "adjoint_run_summary.json"
    )
    summary = json.loads(adjoint_summary.read_text(encoding="utf-8"))
    assert summary["ok"] is False
    assert summary["conversion_mode"] == "execution-failed-no-conversion"
    assert summary["sensitivity_vti"] is None


def test_topology_exploration_resume_reuses_results(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    run_dir = tmp_path / "topology"
    first = run_topology_exploration(
        project_yaml,
        run_dir=run_dir,
        iterations=1,
        seed=5,
        voxel_size_m=0.12,
    )
    result_path = run_dir / "topology_0000" / "topology_result.json"
    mtime = result_path.stat().st_mtime_ns
    time.sleep(0.01)

    second = run_topology_exploration(
        project_yaml,
        run_dir=run_dir,
        iterations=1,
        seed=5,
        voxel_size_m=0.12,
        resume=True,
    )

    assert result_path.stat().st_mtime_ns == mtime
    assert second.candidates[0].density_cell_count == first.candidates[0].density_cell_count


def test_practical_topology_runner_writes_monitoring_artifacts(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    run_dir = tmp_path / "practical"

    summary = run_practical_optimization(
        project_yaml,
        run_dir=run_dir,
        mode="topology",
        iterations=2,
        evaluator="low-fi",
        seed=3,
        voxel_size_m=0.12,
        resume=False,
    )

    progress = json.loads((run_dir / "progress.json").read_text(encoding="utf-8"))
    assert summary.status == "complete"
    assert summary.accepted_count == 2
    assert summary.failure_classes["accepted"] == 2
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "runner_summary.json").exists()
    assert (run_dir / "run_summary.md").exists()
    assert (run_dir / "best_design" / "topology_result.json").exists()
    assert progress["best_objective"] == summary.best_objective


def test_practical_runner_classifies_openfoam_failures_as_cfd() -> None:
    classification = classify_candidate(
        {
            "index": 2,
            "status": "failed",
            "constraints_ok": False,
            "constraint_records": [],
            "rejection_reasons": ["openfoam_timeout: test"],
            "candidate_dir": "candidate_0002",
        }
    )

    assert classification["class"] == "failed_cfd"
    assert classification["primary_reason"] == "openfoam_timeout: test"


def test_practical_parametric_runner_writes_best_export(tmp_path: Path) -> None:
    project_yaml = _write_project(tmp_path / "base", voxel_size_m=0.12)
    run_dir = tmp_path / "practical"

    summary = run_practical_optimization(
        project_yaml,
        run_dir=run_dir,
        mode="parametric",
        iterations=1,
        evaluator="mock",
        seed=3,
        voxel_size_m=0.12,
        resume=False,
    )

    assert summary.mode == "parametric"
    assert summary.status == "complete"
    assert (run_dir / "best_design" / "candidate_result.json").exists()
    assert (run_dir / "parametric" / "optimization_summary.json").exists()


def _write_project(
    tmp_path: Path,
    *,
    include_roots: bool = True,
    forbidden_file: str = "geometry/forbidden_tire_clearance.stl",
    voxel_size_m: float = 0.10,
    enforce_front_ratio: bool = False,
) -> Path:
    write_front_wing_demo_geometry(tmp_path / "geometry")
    roots = [
        {"id": "root_mount_left", "type": "stl", "file": "geometry/root_mount_left.stl"},
        {"id": "root_mount_right", "type": "stl", "file": "geometry/root_mount_right.stl"},
    ] if include_roots else []
    data = {
        "geometry": {
            "fixed_solids": [
                {"id": "vehicle_nose", "file": "geometry/vehicle_nose.stl"},
                {"id": "tire_fl", "file": "geometry/tire_fl.stl"},
                {"id": "tire_fr", "file": "geometry/tire_fr.stl"},
                {"id": "ground", "file": "geometry/ground.stl"},
            ],
            "design_geometry": [
                {"id": "front_wing_initial", "file": "geometry/front_wing_initial.stl"},
            ],
            "design_domains": [
                {"id": "allowed_front_box", "file": "geometry/allowed_front_box.stl"},
            ],
            "forbidden_regions": [
                {"id": "forbidden_tire_clearance", "file": forbidden_file},
            ],
        },
        "roots": roots,
        "grid": {
            "voxel_size_m": voxel_size_m,
            "padding_m": 0.12,
            "band_width_m": 0.20,
            "max_points": 2_000_000,
        },
        "constraints": {
            "min_thickness_mm": 10.0,
            "rule_margin_mm": 5.0,
            "require_eroded_connectivity": True,
            "front_downforce_ratio": {
                "enabled": True,
                "enforce": enforce_front_ratio,
                "x_split_m": 0.0,
                "min": 0.4,
                "max": 0.6,
            },
        },
        "objective": {
            "type": "maximize_downforce_with_efficiency_constraint",
            "efficiency_min": 3.0,
        },
        "operating_point": {
            "velocity_mps": 11.0,
            "density": 1.229,
            "viscosity": 1.73e-5,
        },
        "output_dir": "runs/front_wing_demo",
    }
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return project_yaml
