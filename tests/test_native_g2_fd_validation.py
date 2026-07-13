from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.canonical_grid_snapshot import CANONICAL_MASK_IDS, load_and_verify_canonical_grid_snapshot, write_canonical_grid_snapshot
from cfd_sdf.native_g2_fd_validation import (
    execute_native_g2_openfoam_fd_direction,
    prepare_native_g2_openfoam_fd_direction,
    validate_native_g2_openfoam_fd_direction,
)
from cfd_sdf.openfoam_canonical_field_transfer import reconstruct_and_write_canonical_gradient_transfer
from cfd_sdf.openfoam_grid_transfer import UniformCartesianCellGrid
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256


def test_prepares_and_validates_native_fd_with_declared_force_units(tmp_path: Path) -> None:
    project = _write_project(tmp_path / "project.yaml")
    spec = load_problem_spec(project)
    bundle, baseline = _write_bundle_and_baseline(tmp_path, spec)
    snapshot_path = _write_snapshot(tmp_path, spec)
    gradient = reconstruct_and_write_canonical_gradient_transfer(
        case_dir=baseline,
        adjoint_solver_id="resp_force",
        block_mesh_dict=bundle / "flow_straight/system/blockMeshDict",
        verified_snapshot=load_and_verify_canonical_grid_snapshot(snapshot_path, spec),
        output_directory=tmp_path / "gradient",
    )

    artifacts = prepare_native_g2_openfoam_fd_direction(
        project_yaml=project,
        bundle_dir=bundle,
        baseline_case_dir=baseline,
        canonical_snapshot_json=snapshot_path,
        canonical_gradient_dir=gradient.directory,
        flow_case_id="straight",
        response_id="force",
        objective_id="force_objective",
        canonical_density_direction=np.array([0.2, 0.4]),
        epsilon=0.1,
        output_dir=tmp_path / "fd",
    )

    with np.load(artifacts.direction_npz, allow_pickle=False) as payload:
        assert payload["source_alpha_direction"] == pytest.approx([0.3])
        assert payload["plus_source_alpha"] == pytest.approx([0.53])
        assert payload["minus_source_alpha"] == pytest.approx([0.47])
    assert "nonuniform List<scalar>" in (artifacts.plus_case_dir / "0.orig/alpha").read_text(encoding="utf-8")
    assert "cp 0.orig/alpha 0/alpha" in (artifacts.plus_case_dir / "Allrun").read_text(encoding="utf-8")

    # Raw porousDirectionalForce coefficients.  The declared conversion is
    # 100 N/coefficient and the selected objective coefficient is 0.7.
    _write_objective(artifacts.plus_case_dir, "force", 0.06)
    _write_objective(artifacts.minus_case_dir, "force", -0.06)
    result = validate_native_g2_openfoam_fd_direction(artifacts.output_dir, relative_error_tolerance=1.0e-12)

    assert result.ok
    assert result.units == "N"
    assert result.finite_difference_derivative == pytest.approx(42.0)
    assert result.adjoint_directional_derivative == pytest.approx(42.0)
    assert result.report_json.exists()


def test_rejects_direction_outside_active_mask_and_bounds_without_clipping(tmp_path: Path) -> None:
    project = _write_project(tmp_path / "project.yaml")
    spec = load_problem_spec(project)
    bundle, baseline = _write_bundle_and_baseline(tmp_path, spec)
    snapshot_path = _write_snapshot(tmp_path, spec, active=np.array([1, 0], dtype=np.uint8))
    gradient = reconstruct_and_write_canonical_gradient_transfer(
        case_dir=baseline,
        adjoint_solver_id="resp_force",
        block_mesh_dict=bundle / "flow_straight/system/blockMeshDict",
        verified_snapshot=load_and_verify_canonical_grid_snapshot(snapshot_path, spec),
        output_directory=tmp_path / "gradient",
    )

    with pytest.raises(ValueError, match="zero outside active"):
        prepare_native_g2_openfoam_fd_direction(
            project_yaml=project,
            bundle_dir=bundle,
            baseline_case_dir=baseline,
            canonical_snapshot_json=snapshot_path,
            canonical_gradient_dir=gradient.directory,
            flow_case_id="straight",
            response_id="force",
            objective_id="force_objective",
            canonical_density_direction=np.array([0.2, 0.4]),
            epsilon=0.1,
            output_dir=tmp_path / "inactive",
        )

    # The direction is active, but a symmetric perturbation would pass alpha=1.
    snapshot_path = _write_snapshot(tmp_path / "other", spec)
    gradient = reconstruct_and_write_canonical_gradient_transfer(
        case_dir=baseline,
        adjoint_solver_id="resp_force",
        block_mesh_dict=bundle / "flow_straight/system/blockMeshDict",
        verified_snapshot=load_and_verify_canonical_grid_snapshot(snapshot_path, spec),
        output_directory=tmp_path / "gradient_other",
    )
    with pytest.raises(ValueError, match="clipping is forbidden"):
        prepare_native_g2_openfoam_fd_direction(
            project_yaml=project,
            bundle_dir=bundle,
            baseline_case_dir=baseline,
            canonical_snapshot_json=snapshot_path,
            canonical_gradient_dir=gradient.directory,
            flow_case_id="straight",
            response_id="force",
            objective_id="force_objective",
            canonical_density_direction=np.array([1.0, 1.0]),
            epsilon=2.0,
            output_dir=tmp_path / "bounds",
        )


def test_rejects_gradient_from_a_different_baseline_and_supports_injected_runner(tmp_path: Path) -> None:
    project = _write_project(tmp_path / "project.yaml")
    spec = load_problem_spec(project)
    bundle, baseline = _write_bundle_and_baseline(tmp_path, spec)
    snapshot_path = _write_snapshot(tmp_path, spec)
    gradient = reconstruct_and_write_canonical_gradient_transfer(
        case_dir=baseline,
        adjoint_solver_id="resp_force",
        block_mesh_dict=bundle / "flow_straight/system/blockMeshDict",
        verified_snapshot=load_and_verify_canonical_grid_snapshot(snapshot_path, spec),
        output_directory=tmp_path / "gradient",
    )
    changed = _write_baseline(tmp_path / "changed", sensitivity=3.0)
    with pytest.raises(ValueError, match="topOSens does not match"):
        prepare_native_g2_openfoam_fd_direction(
            project_yaml=project,
            bundle_dir=bundle,
            baseline_case_dir=changed,
            canonical_snapshot_json=snapshot_path,
            canonical_gradient_dir=gradient.directory,
            flow_case_id="straight",
            response_id="force",
            objective_id="force_objective",
            canonical_density_direction=np.array([0.2, 0.4]),
            epsilon=0.1,
            output_dir=tmp_path / "mismatch",
        )

    artifacts = prepare_native_g2_openfoam_fd_direction(
        project_yaml=project,
        bundle_dir=bundle,
        baseline_case_dir=baseline,
        canonical_snapshot_json=snapshot_path,
        canonical_gradient_dir=gradient.directory,
        flow_case_id="straight",
        response_id="force",
        objective_id="force_objective",
        canonical_density_direction=np.array([0.2, 0.4]),
        epsilon=0.1,
        output_dir=tmp_path / "injected",
    )
    calls: list[Path] = []

    def injected(case: Path) -> str:
        calls.append(case)
        return "completed externally"

    assert execute_native_g2_openfoam_fd_direction(artifacts, runner=injected) == (
        "completed externally",
        "completed externally",
    )
    assert calls == [artifacts.plus_case_dir, artifacts.minus_case_dir]


def _write_project(path: Path) -> Path:
    path.write_text(
        """schema_version: 2
problem_id: fd_test
units: {length: m, time: s, mass: kg}
coordinate_frame:
  id: global
  origin_m: [0, 0, 0]
  basis: {x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1]}
grid:
  kind: uniform_cartesian
  voxel_size_m: 1
  padding_m: 0
  domain_bounds_m: {lower: [0, 0, 0], upper: [2, 1, 1]}
reference_values: {area_m2: 2.0, length_m: 1.0, moment_center_m: [0, 0, 0]}
geometry_regions: []
flow_cases:
  - id: straight
    freestream_velocity_mps: [10, 0, 0]
    fluid: {model: incompressible_newtonian, density_kg_m3: 1.0, dynamic_viscosity_pa_s: 0.001}
    boundary_conditions: {inlet: freestream, outlet: pressure_outlet}
responses:
  - id: force
    kind: force
    flow_case_id: straight
    direction: [1, 0, 0]
objectives:
  - id: force_objective
    sense: minimize
    terms: [{coefficient: 0.7, flow_case_id: straight, response_id: force}]
constraints: []
topology_policy:
  root_groups: []
  solid_connectivity: {mode: disabled, required_root_group_ids: [], max_components: null, evaluate_eroded: false}
  void_connectivity: {mode: disabled, required_root_group_ids: [], max_components: null, evaluate_eroded: false}
  minimum_solid_width_m: null
  minimum_void_width_m: null
  minimum_gap_m: null
  erosion_radius_m: null
""",
        encoding="utf-8",
    )
    return path


def _write_snapshot(directory: Path, spec, active: np.ndarray | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    grid = UniformCartesianCellGrid(origin=(0, 0, 0), spacing=(1, 1, 1), cell_shape=(2, 1, 1))
    masks = {mask: np.ones(2, dtype=np.uint8) for mask in CANONICAL_MASK_IDS}
    masks["active_design_mask"] = np.ones(2, dtype=np.uint8) if active is None else active
    return write_canonical_grid_snapshot(spec, grid=grid, masks=masks, path=directory / "snapshot.json")


def _write_bundle_and_baseline(root: Path, spec) -> tuple[Path, Path]:
    bundle = root / "bundle"
    case = bundle / "flow_straight"
    (case / "system").mkdir(parents=True)
    (case / "0.orig").mkdir()
    _write_block_mesh(case / "system/blockMeshDict")
    (case / "0.orig/alpha").write_text(_alpha_template(), encoding="utf-8")
    (case / "Allrun").write_text("#!/bin/sh\nrunApplication setFields\nrunApplication solver\n", encoding="utf-8")
    (case / "openfoam_case_compilation.json").write_text("{}", encoding="utf-8")
    (bundle / "openfoam_case_bundle.json").write_text(
        json.dumps(
            {
                "kind": "openfoam_case_bundle",
                "status": "compiled",
                "compile_ready": True,
                "problem_id": spec.problem_id,
                "problem_spec_sha256": problem_spec_sha256(spec),
                "flow_cases": {"straight": {"case_dir": "flow_straight"}},
            }
        ),
        encoding="utf-8",
    )
    return bundle, _write_baseline(root / "baseline")


def _write_baseline(case: Path, sensitivity: float = 2.0) -> Path:
    root = case / "processor0"
    (root / "constant/polyMesh").mkdir(parents=True)
    (root / "constant/polyMesh/cellProcAddressing").write_text(_labels([0]), encoding="utf-8")
    (root / "1").mkdir()
    (root / "1/topOSensresp_force").write_text(_field("topOSensresp_force", [sensitivity]), encoding="utf-8")
    (root / "1/alphaTilda").write_text(_field("alphaTilda", [0.5]), encoding="utf-8")
    (root / "1/beta").write_text(_field("beta", [0.5]), encoding="utf-8")
    (root / "0").mkdir()
    (root / "0/alpha").write_text(_uniform_alpha(0.5), encoding="utf-8")
    return case


def _write_block_mesh(path: Path) -> None:
    path.write_text(
        """scale 1;
vertices
(
    (0 0 0) (2 0 0) (2 1 0) (0 1 0)
    (0 0 1) (2 0 1) (2 1 1) (0 1 1)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) (1 1 1) simpleGrading (1 1 1)
);
edges
(
);
""",
        encoding="utf-8",
    )


def _field(name: str, values: list[float]) -> str:
    return "FoamFile\n{\n class volScalarField;\n object " + name + ";\n}\n" + "dimensions [0 0 0 0 0 0 0];\ninternalField nonuniform List<scalar> " + str(len(values)) + "\n(\n" + "\n".join(str(value) for value in values) + "\n);\n"


def _labels(values: list[int]) -> str:
    return "FoamFile\n{\n class labelList;\n object cellProcAddressing;\n}\n" + str(len(values)) + "\n(\n" + "\n".join(str(value) for value in values) + "\n);\n"


def _uniform_alpha(value: float) -> str:
    return "FoamFile\n{\n class volScalarField;\n object alpha;\n}\n" + f"dimensions [0 0 0 0 0 0 0];\ninternalField uniform {value};\n"


def _alpha_template() -> str:
    return "FoamFile\n{\n class volScalarField;\n object alpha;\n}\n" + "dimensions [0 0 0 0 0 0 0];\ninternalField uniform 0;\nboundaryField\n{\n}\n"


def _write_objective(case: Path, response_id: str, value: float) -> None:
    path = case / "optimisation/objective" / response_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"0 0 {value}\n", encoding="utf-8")
