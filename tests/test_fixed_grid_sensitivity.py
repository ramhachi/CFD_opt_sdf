from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import pyvista as pv

from cfd_sdf.fixed_grid_contract import (
    FIXED_GRID_CONTRACT_SCHEMA_VERSION,
    CartesianCellGrid,
    _write_cell_vti,
)
from cfd_sdf.fixed_grid_primal import prepare_fixed_grid_primal_case
from cfd_sdf.fixed_grid_sensitivity import (
    build_fixed_grid_sensitivity_from_primal_case,
    read_openfoam_vol_scalar_field,
    run_fixed_grid_sensitivity_direction_suite,
    validate_fixed_grid_sensitivity_direction,
)


def test_extract_fixed_grid_sensitivity_reads_openfoam_fields_and_combines_constraint(
    tmp_path: Path,
) -> None:
    topology_state = _write_fixed_grid_state(tmp_path / "contract")
    template = _write_template_case(tmp_path / "template")
    artifacts = prepare_fixed_grid_primal_case(
        topology_state,
        case_dir=tmp_path / "case",
        template_case_dir=template,
        density_variant="seed",
    )
    drag = np.linspace(-1.0, 2.0, 12)
    downforce = np.linspace(0.5, -0.5, 12)
    _write_openfoam_scalar(artifacts.case_dir / "1" / "topOSensas1.gz", "topOSensas1", drag)
    _write_openfoam_scalar(
        artifacts.case_dir / "1" / "topOSensdownforce.gz",
        "topOSensdownforce",
        downforce,
    )
    _write_primal_summary(artifacts.case_dir, drag=1.2, downforce=0.4)

    sensitivity = build_fixed_grid_sensitivity_from_primal_case(
        artifacts.case_dir,
        efficiency_min=4.0,
    )

    assert sensitivity.sensitivity_vti.exists()
    assert sensitivity.sensitivity_summary_json.exists()
    mesh = pv.read(sensitivity.sensitivity_vti)
    assert set(mesh.cell_data) >= {
        "d_drag_d_rho",
        "d_downforce_d_rho",
        "d_efficiency_constraint_d_rho",
        "d_connectivity_nominal_d_rho",
        "d_connectivity_eroded_d_rho",
        "active_design_mask",
    }
    active = mesh.cell_data["active_design_mask"] > 0
    assert np.all(mesh.cell_data["d_drag_d_rho"][~active] == 0.0)
    assert np.allclose(
        mesh.cell_data["d_efficiency_constraint_d_rho"],
        4.0 * mesh.cell_data["d_drag_d_rho"]
        - mesh.cell_data["d_downforce_d_rho"],
    )
    summary = json.loads(sensitivity.sensitivity_summary_json.read_text(encoding="utf-8"))
    assert summary["roadmap_phase"] == "T3"
    assert summary["status"] == "extracted"
    assert summary["connectivity_derivative_status"] == "not_evaluated_t3_aero_only"


def test_validate_fixed_grid_sensitivity_direction_compares_plus_minus_cases(
    tmp_path: Path,
) -> None:
    topology_state = _write_fixed_grid_state(tmp_path / "contract")
    template = _write_template_case(tmp_path / "template")
    baseline = prepare_fixed_grid_primal_case(
        topology_state,
        case_dir=tmp_path / "baseline",
        template_case_dir=template,
        density_variant="seed",
    )
    drag = np.zeros(12)
    drag[4] = 2.0
    drag[5] = -0.5
    downforce = np.zeros(12)
    _write_openfoam_scalar(baseline.case_dir / "1" / "topOSensas1.gz", "topOSensas1", drag)
    _write_openfoam_scalar(
        baseline.case_dir / "1" / "topOSensdownforce.gz",
        "topOSensdownforce",
        downforce,
    )
    _write_primal_summary(baseline.case_dir, drag=0.0, downforce=0.0)
    sensitivity = build_fixed_grid_sensitivity_from_primal_case(baseline.case_dir)

    plus = tmp_path / "plus"
    minus = tmp_path / "minus"
    shutil.copytree(baseline.case_dir, plus)
    shutil.copytree(baseline.case_dir, minus)
    epsilon = 0.01
    base_density = pv.read(baseline.input_density_vti).cell_data["rho_input"].astype(float)
    direction = np.zeros_like(base_density)
    direction[4] = 1.0
    direction[5] = -2.0
    _write_density_input(plus / "fixed_grid_input_density.vti", base_density + epsilon * direction)
    _write_density_input(minus / "fixed_grid_input_density.vti", base_density - epsilon * direction)
    adjoint_direction = float(np.dot(drag, direction))
    _write_primal_summary(plus, drag=epsilon * adjoint_direction, downforce=0.0)
    _write_primal_summary(minus, drag=-epsilon * adjoint_direction, downforce=0.0)

    result = validate_fixed_grid_sensitivity_direction(
        baseline.case_dir,
        plus,
        minus,
        sensitivity_vti=sensitivity.sensitivity_vti,
        output_dir=tmp_path / "direction_check",
        objective="drag",
        epsilon=epsilon,
        relative_error_tolerance=1.0e-6,
    )

    assert result.ok is True
    assert result.perturbed_cell_count == 2
    assert result.finite_difference_derivative == pytest.approx(adjoint_direction)
    assert result.adjoint_directional_derivative == pytest.approx(adjoint_direction)
    assert result.report_json.exists()
    assert result.direction_vti.exists()


def test_run_fixed_grid_sensitivity_direction_suite_dry_run_writes_plus_minus_cases(
    tmp_path: Path,
) -> None:
    topology_state = _write_fixed_grid_state(tmp_path / "contract")
    template = _write_template_case(tmp_path / "template")
    baseline = prepare_fixed_grid_primal_case(
        topology_state,
        case_dir=tmp_path / "baseline",
        template_case_dir=template,
        density_variant="seed",
    )
    drag = np.zeros(12)
    drag[4] = 2.0
    downforce = np.zeros(12)
    _write_openfoam_scalar(baseline.case_dir / "1" / "topOSensas1.gz", "topOSensas1", drag)
    _write_openfoam_scalar(
        baseline.case_dir / "1" / "topOSensdownforce.gz",
        "topOSensdownforce",
        downforce,
    )
    _write_primal_summary(baseline.case_dir, drag=0.0, downforce=0.0)
    sensitivity = build_fixed_grid_sensitivity_from_primal_case(baseline.case_dir)

    suite = run_fixed_grid_sensitivity_direction_suite(
        baseline.case_dir,
        run_dir=tmp_path / "direction_suite",
        sensitivity_vti=sensitivity.sensitivity_vti,
        objective="drag",
        direction_mode="cellwise",
        cell_index=4,
        epsilon=0.01,
        template_case_dir=template,
        execute=False,
    )

    assert suite.summary["status"] == "prepared"
    assert suite.summary["ok"] is True
    assert suite.direction_vti.exists()
    assert suite.direction_summary_json.exists()
    assert suite.plus_topology_state_json.exists()
    assert suite.minus_topology_state_json.exists()
    assert suite.plus_case.input_density_vti.exists()
    assert suite.minus_case.input_density_vti.exists()
    plus_density = pv.read(suite.plus_case.input_density_vti).cell_data["rho_input"]
    minus_density = pv.read(suite.minus_case.input_density_vti).cell_data["rho_input"]
    assert plus_density[4] == pytest.approx(0.51)
    assert minus_density[4] == pytest.approx(0.49)
    plus_allrun = (suite.plus_case.case_dir / "Allrun").read_text(encoding="utf-8")
    assert "snappyHexMesh" not in plus_allrun
    assert "setFields" not in plus_allrun


def test_read_openfoam_vol_scalar_field_rejects_wrong_value_count(tmp_path: Path) -> None:
    path = tmp_path / "badField"
    path.write_text(
        _openfoam_scalar_text("badField", np.array([1.0, 2.0])).replace("2\n(", "3\n("),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected 3"):
        read_openfoam_vol_scalar_field(path)


def _write_fixed_grid_state(directory: Path) -> Path:
    directory.mkdir(parents=True)
    image = pv.ImageData(
        dimensions=(4, 3, 3),
        spacing=(0.5, 0.4, 0.3),
        origin=(-1.0, -0.4, -0.3),
    )
    count = image.n_cells
    rho = np.zeros(count, dtype=np.float32)
    rho[[4, 5, 6]] = 0.5
    allowed = np.ones(count, dtype=np.uint8)
    active = np.ones(count, dtype=np.uint8)
    allowed[[0, 3]] = 0
    active[[0, 3]] = 0
    density_arrays = {
        "rho": rho,
        "rho_filtered": rho,
        "rho_projected": rho,
        "alpha": 100.0 * rho,
        "allowed_mask": allowed,
        "forbidden_mask": np.zeros(count, dtype=np.uint8),
        "fixed_solid_mask": np.zeros(count, dtype=np.uint8),
        "root_mask": np.zeros(count, dtype=np.uint8),
        "active_design_mask": active,
    }
    grid = CartesianCellGrid(
        origin=tuple(float(value) for value in image.origin),
        spacing=tuple(float(value) for value in image.spacing),
        cell_shape=(3, 2, 2),
    )
    _write_cell_vti(grid, density_arrays, directory / "density.vti", kind="fixed_grid_density")
    vtk_dir = directory / "source_vtk"
    vtk_dir.mkdir()
    source = image.cast_to_unstructured_grid()
    source.cell_data["alpha"] = rho
    source.save(vtk_dir / "internal.vtu")
    state = {
        "schema_version": FIXED_GRID_CONTRACT_SCHEMA_VERSION,
        "kind": "fixed_grid_topology_state",
        "design_variable": "rho",
        "grid": grid.to_dict(),
        "density_vti": "density.vti",
        "source_solver": {
            "case_dir": str(directory / "template_placeholder"),
            "initial_vtk": str(vtk_dir / "internal.vtu"),
        },
    }
    path = directory / "topology_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def _write_template_case(case_dir: Path) -> Path:
    for relative in ("0.orig", "constant", "system"):
        (case_dir / relative).mkdir(parents=True)
    (case_dir / "0.orig" / "alpha").write_text(
        "FoamFile\n{\n    class volScalarField;\n    object alpha;\n}\n"
        "dimensions [0 0 0 0 0 0 0];\n"
        "internalField uniform 0;\n"
        "boundaryField\n"
        "{\n"
        "    inlet { type zeroGradient; }\n"
        "    outlet { type zeroGradient; }\n"
        "    spanMin { type symmetryPlane; }\n"
        "    spanMax { type symmetryPlane; }\n"
        "    lower { type symmetryPlane; }\n"
        "    upper { type symmetryPlane; }\n"
        "}\n",
        encoding="utf-8",
    )
    (case_dir / "0.orig" / "U").write_text("", encoding="utf-8")
    (case_dir / "0.orig" / "p").write_text("", encoding="utf-8")
    (case_dir / "system" / "optimisationDict").write_text(
        "primalSolvers { op1 { solutionControls { nIters 1000; } } }\n"
        "adjointManagers { adjManager1 { adjointSolvers { as1 { solutionControls { nIters 4000; } } } } }\n"
        "optimisation { designVariables { fixedZeroPorousZones ( oldZone ); betaMax 100; } }\n",
        encoding="utf-8",
    )
    (case_dir / "system" / "controlDict").write_text(
        "application adjointOptimisationFoam;\nlibs (\"libcfdSdfPorousObjectives.so\");\n",
        encoding="utf-8",
    )
    return case_dir


def _write_openfoam_scalar(path: Path, object_name: str, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            stream.write(_openfoam_scalar_text(object_name, values))
    else:
        path.write_text(_openfoam_scalar_text(object_name, values), encoding="utf-8")


def _openfoam_scalar_text(object_name: str, values: np.ndarray) -> str:
    value_text = "\n".join(f"{float(value):.12g}" for value in values)
    return (
        "FoamFile\n"
        "{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        "    class       volScalarField;\n"
        f"    object      {object_name};\n"
        "}\n"
        "dimensions      [0 0 0 0 0 0 0];\n"
        "internalField   nonuniform List<scalar>\n"
        f"{len(values)}\n"
        "(\n"
        f"{value_text}\n"
        ")\n"
        ";\n"
        "boundaryField {}\n"
    )


def _write_primal_summary(case_dir: Path, *, drag: float, downforce: float) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "kind": "fixed_grid_primal_summary",
        "efficiency_min": 3.0,
        "drag_coefficient": drag,
        "downforce_coefficient": downforce,
        "objective": -downforce,
        "efficiency_constraint": 3.0 * drag - downforce,
    }
    (case_dir / "fixed_grid_primal_summary.json").write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def _write_density_input(path: Path, density: np.ndarray) -> None:
    grid = CartesianCellGrid(
        origin=(-1.0, -0.4, -0.3),
        spacing=(0.5, 0.4, 0.3),
        cell_shape=(3, 2, 2),
    )
    _write_cell_vti(
        grid,
        {
            "rho_input": np.asarray(density, dtype=np.float32),
            "active_design_mask": np.ones(density.size, dtype=np.uint8),
        },
        path,
        kind="fixed_grid_primal_input",
    )
