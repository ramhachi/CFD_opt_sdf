from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh

from cfd_sdf.config import load_project
from cfd_sdf.fixed_grid_contract import (
    DENSITY_ARRAYS,
    SENSITIVITY_ARRAYS,
    _point_data_to_cell_min,
    build_fixed_grid_contract_from_density_design_state,
    build_openfoam_fixed_grid_contract,
    validate_fixed_grid_contract,
)
from cfd_sdf.sdf import build_fields


def test_build_openfoam_fixed_grid_contract_writes_t1_artifacts(
    tmp_path: Path,
) -> None:
    case_dir = _write_contract_case(tmp_path / "case")
    validations = _write_validation_reports(tmp_path / "validation")

    artifacts = build_openfoam_fixed_grid_contract(
        case_dir,
        output_dir=tmp_path / "contract",
        efficiency_min=3.0,
        drag_validation_json=validations["drag"],
        downforce_validation_json=validations["downforce"],
        efficiency_validation_json=validations["efficiency"],
    )

    assert artifacts.ok is True
    assert artifacts.validation["status"] == "pass"
    for path in (
        artifacts.topology_state_json,
        artifacts.density_vti,
        artifacts.case_summary_json,
        artifacts.primal_summary_json,
        artifacts.sensitivity_vti,
        artifacts.sensitivity_summary_json,
        artifacts.connectivity_state_vti,
        artifacts.iteration_result_json,
        artifacts.validation_json,
    ):
        assert path.exists()

    density = pv.read(artifacts.density_vti)
    sensitivity = pv.read(artifacts.sensitivity_vti)
    assert density.dimensions == (4, 3, 3)
    assert np.allclose(density.spacing, (0.5, 0.4, 0.3))
    assert set(DENSITY_ARRAYS) <= set(density.cell_data)
    assert set(SENSITIVITY_ARRAYS) <= set(sensitivity.cell_data)
    assert np.count_nonzero(density.cell_data["active_design_mask"]) == 10
    assert np.all(density.cell_data["active_design_mask"][[0, 3]] == 0)
    assert np.allclose(
        density.cell_data["alpha"],
        100.0 * density.cell_data["rho_projected"],
    )
    assert np.allclose(
        sensitivity.cell_data["d_efficiency_constraint_d_rho"],
        3.0 * sensitivity.cell_data["d_drag_d_rho"]
        - sensitivity.cell_data["d_downforce_d_rho"],
    )

    state = json.loads(artifacts.topology_state_json.read_text(encoding="utf-8"))
    assert state["kind"] == "fixed_grid_topology_state"
    assert state["grid"]["location"] == "cell"
    assert state["grid"]["cell_order"] == "vtk-x-fastest"
    assert state["connectivity_status"] == "not_evaluated_t1_contract_only"
    assert set(state["array_metadata"]) == set(DENSITY_ARRAYS)
    summary = json.loads(
        artifacts.sensitivity_summary_json.read_text(encoding="utf-8")
    )
    assert summary["status"] == "validated"
    assert set(summary["array_metadata"]) == set(SENSITIVITY_ARRAYS)


def test_validate_fixed_grid_contract_detects_missing_array(
    tmp_path: Path,
) -> None:
    case_dir = _write_contract_case(tmp_path / "case")
    artifacts = build_openfoam_fixed_grid_contract(
        case_dir,
        output_dir=tmp_path / "contract",
    )
    sensitivity = pv.read(artifacts.sensitivity_vti)
    del sensitivity.cell_data["d_drag_d_rho"]
    sensitivity.save(artifacts.sensitivity_vti)

    result = validate_fixed_grid_contract(artifacts.topology_state_json)

    assert result["ok"] is False
    assert any(
        "fixed_grid_sensitivity.vti is missing arrays: d_drag_d_rho" in error
        for error in result["errors"]
    )


def test_validate_fixed_grid_contract_detects_grid_and_mask_mismatch(
    tmp_path: Path,
) -> None:
    case_dir = _write_contract_case(tmp_path / "case")
    artifacts = build_openfoam_fixed_grid_contract(
        case_dir,
        output_dir=tmp_path / "contract",
    )
    sensitivity = pv.read(artifacts.sensitivity_vti)
    sensitivity.spacing = (0.6, 0.4, 0.3)
    active = np.asarray(
        sensitivity.cell_data["active_design_mask"],
        dtype=np.uint8,
    ).copy()
    active[0] = 1
    sensitivity.cell_data["active_design_mask"] = active
    sensitivity.save(artifacts.sensitivity_vti)

    result = validate_fixed_grid_contract(artifacts.topology_state_json)

    assert result["ok"] is False
    assert any("Grid spacing mismatch" in error for error in result["errors"])
    assert any(
        "density and sensitivity active_design_mask arrays do not match" in error
        for error in result["errors"]
    )


def test_build_fixed_grid_contract_from_legacy_density_design_state(
    tmp_path: Path,
) -> None:
    design_state_json = _write_legacy_density_design_state(tmp_path / "legacy")

    artifacts = build_fixed_grid_contract_from_density_design_state(
        design_state_json,
        output_dir=tmp_path / "contract",
        beta_max=100.0,
    )

    assert artifacts.ok is True
    density = pv.read(artifacts.density_vti)
    assert density.dimensions == (3, 3, 3)
    assert set(DENSITY_ARRAYS) <= set(density.cell_data)
    assert np.allclose(
        density.cell_data["alpha"],
        100.0 * density.cell_data["rho_projected"],
    )
    assert np.count_nonzero(density.cell_data["active_design_mask"]) == 8
    sensitivity = pv.read(artifacts.sensitivity_vti)
    assert set(SENSITIVITY_ARRAYS) <= set(sensitivity.cell_data)
    assert np.linalg.norm(sensitivity.cell_data["d_drag_d_rho"]) == 0.0
    state = json.loads(artifacts.topology_state_json.read_text(encoding="utf-8"))
    assert state["source_solver"]["backend"] == "legacy-density-design-state"


def test_point_data_to_cell_min_preserves_thin_root_touch() -> None:
    dimensions = (3, 3, 3)
    values = np.ones(int(np.prod(dimensions)), dtype=np.float64)
    point = values.reshape(dimensions, order="F")
    point[1, 1, 1] = -0.01

    cell_min = _point_data_to_cell_min(values, dimensions)

    assert np.count_nonzero(cell_min <= 0.0) == 8


def test_legacy_density_conversion_preserves_small_project_root(
    tmp_path: Path,
) -> None:
    project_yaml = _write_small_root_project(tmp_path / "project")
    config = load_project(project_yaml)
    bundle = build_fields(config)
    design_state_json = _write_density_state_matching_bundle(
        tmp_path / "legacy",
        bundle,
        source_project=project_yaml,
    )

    artifacts = build_fixed_grid_contract_from_density_design_state(
        design_state_json,
        output_dir=tmp_path / "contract",
        project_yaml=project_yaml,
    )

    density = pv.read(artifacts.density_vti)
    assert np.count_nonzero(density.cell_data["root_mask"]) > 0


def _write_contract_case(case_dir: Path) -> Path:
    vtk_zero = case_dir / "VTK" / "case_0"
    vtk_one = case_dir / "VTK" / "case_1"
    objective_dir = case_dir / "optimisation" / "objective" / "0"
    system_dir = case_dir / "system"
    poly_mesh = case_dir / "constant" / "polyMesh"
    for path in (vtk_zero, vtk_one, objective_dir, system_dir, poly_mesh):
        path.mkdir(parents=True, exist_ok=True)

    image = pv.ImageData(
        dimensions=(4, 3, 3),
        spacing=(0.5, 0.4, 0.3),
        origin=(-1.0, -0.4, -0.3),
    )
    count = image.n_cells
    rho = np.zeros(count, dtype=np.float32)
    rho[[4, 5, 6, 7]] = 0.5
    initial = image.cast_to_unstructured_grid()
    initial.cell_data["alpha"] = rho
    initial.save(vtk_zero / "internal.vtu")

    active = np.ones(count, dtype=bool)
    active[[0, 3]] = False
    drag = np.linspace(0.1, 1.2, count, dtype=np.float32)
    downforce = np.linspace(-0.5, 0.6, count, dtype=np.float32)
    drag[~active] = 0.0
    downforce[~active] = 0.0
    final = image.cast_to_unstructured_grid()
    final.cell_data["alphaTilda"] = np.clip(rho + 0.1, 0.0, 1.0)
    final.cell_data["beta"] = np.clip(rho * 0.8, 0.0, 1.0)
    final.cell_data["topOSensas1"] = drag
    final.cell_data["topOSensdownforce"] = downforce
    final.cell_data["U"] = np.tile(
        np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
        (count, 1),
    )
    final.cell_data["p"] = np.linspace(-1.0, 1.0, count, dtype=np.float32)
    final.save(vtk_one / "internal.vtu")

    (system_dir / "optimisationDict").write_text(
        "fixedZeroPorousZones (fixedBuffer);\n"
        "betaMax 100;\n",
        encoding="utf-8",
    )
    cell_zones = (
        "1\n(\n"
        "fixedBuffer\n"
        "{\n"
        "    type cellZone;\n"
        "    cellLabels List<label>\n"
        "    2\n"
        "    (\n"
        "    0\n"
        "    3\n"
        "    )\n"
        "    ;\n"
        "}\n"
        ")\n"
    )
    with gzip.open(poly_mesh / "cellZones.gz", "wt", encoding="utf-8") as stream:
        stream.write(cell_zones)

    _write_objective(objective_dir / "dragas1", 0.4)
    _write_objective(objective_dir / "downforcedownforce", 0.9)
    (case_dir / "log.adjointOptimisationFoam").write_text(
        "op1 solution converged in 10 iterations\n"
        "as1 solution converged in 20 iterations\n"
        "downforce solution converged in 30 iterations\n"
        "\nEnd\n\n"
        "Finalising parallel run\n",
        encoding="utf-8",
    )
    return case_dir


def _write_legacy_density_design_state(directory: Path) -> Path:
    directory.mkdir(parents=True)
    image = pv.ImageData(
        dimensions=(3, 3, 3),
        spacing=(0.2, 0.2, 0.2),
        origin=(-0.2, -0.2, -0.2),
    )
    values = np.ones(image.n_points, dtype=np.float32)
    allowed = np.ones(image.n_points, dtype=np.uint8)
    image.point_data["density"] = values
    image.point_data["allowed_mask"] = allowed
    image.save(directory / "density.vti")
    data = {
        "schema_version": 1,
        "kind": "density_design_state",
        "design_variable": "density",
        "density_vti": "density.vti",
        "density_array": "density",
        "allowed_array": "allowed_mask",
        "grid": {
            "origin": list(image.origin),
            "spacing": image.spacing[0],
            "shape": list(image.dimensions),
            "bounds": [[-0.2, -0.2, -0.2], [0.2, 0.2, 0.2]],
        },
        "bounds": {"lower": 0.0, "upper": 1.0, "min": 1.0, "max": 1.0},
        "iso_value": 0.5,
        "derived_geometry": "front_wing_initial.stl",
        "source_project": "project.yaml",
        "created_by": "test",
    }
    path = directory / "design_state.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _write_small_root_project(project_dir: Path) -> Path:
    geometry_dir = project_dir / "geometry"
    geometry_dir.mkdir(parents=True)
    _write_box(geometry_dir / "allowed.stl", center=(0.0, 0.0, 0.0), extents=(1.0, 1.0, 1.0))
    _write_box(geometry_dir / "design.stl", center=(0.0, 0.0, 0.0), extents=(0.4, 0.4, 0.4))
    _write_box(geometry_dir / "root.stl", center=(0.08, 0.08, 0.08), extents=(0.08, 0.08, 0.08))
    project_yaml = project_dir / "project.yaml"
    project_yaml.write_text(
        "\n".join(
            [
                "geometry:",
                "  design_geometry:",
                "  - id: design",
                "    file: geometry/design.stl",
                "  design_domains:",
                "  - id: allowed",
                "    file: geometry/allowed.stl",
                "roots:",
                "- id: small_root",
                "  type: stl",
                "  file: geometry/root.stl",
                "grid:",
                "  voxel_size_m: 0.2",
                "  padding_m: 0.0",
                "  band_width_m: 0.2",
                "  max_points: 100000",
                "output_dir: runs/test",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return project_yaml


def _write_density_state_matching_bundle(
    directory: Path,
    bundle: object,
    *,
    source_project: Path,
) -> Path:
    directory.mkdir(parents=True)
    image = pv.ImageData(
        dimensions=tuple(int(value) for value in bundle.grid.shape),
        spacing=(bundle.grid.spacing, bundle.grid.spacing, bundle.grid.spacing),
        origin=tuple(float(value) for value in bundle.grid.origin),
    )
    image.point_data["density"] = np.ones(image.n_points, dtype=np.float32)
    image.point_data["allowed_mask"] = np.ones(image.n_points, dtype=np.uint8)
    image.save(directory / "density.vti")
    data = {
        "schema_version": 1,
        "kind": "density_design_state",
        "design_variable": "density",
        "density_vti": "density.vti",
        "density_array": "density",
        "allowed_array": "allowed_mask",
        "grid": {
            "origin": list(image.origin),
            "spacing": image.spacing[0],
            "shape": list(image.dimensions),
            "bounds": [list(bundle.grid.bounds[0]), list(bundle.grid.bounds[1])],
        },
        "bounds": {"lower": 0.0, "upper": 1.0, "min": 1.0, "max": 1.0},
        "iso_value": 0.5,
        "derived_geometry": "front_wing_initial.stl",
        "source_project": str(source_project),
        "created_by": "test",
    }
    path = directory / "design_state.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _write_box(
    path: Path,
    *,
    center: tuple[float, float, float],
    extents: tuple[float, float, float],
) -> None:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    mesh.export(path)


def _write_objective(path: Path, value: float) -> None:
    path.write_text(
        f"# J JCycle\n1 {value:.12g} {value:.12g}\n",
        encoding="utf-8",
    )


def _write_validation_reports(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True)
    paths: dict[str, Path] = {}
    for name in ("drag", "downforce", "efficiency"):
        path = directory / f"{name}.json"
        path.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "sign_match": True,
                    "relative_error": 0.01,
                    "relative_error_tolerance": 0.1,
                }
            ),
            encoding="utf-8",
        )
        paths[name] = path
    return paths
