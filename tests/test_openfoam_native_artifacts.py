from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from cfd_sdf.fixed_grid_artifacts import (
    read_fixed_grid_primal_summary,
    read_fixed_grid_sensitivity_summary,
)
from cfd_sdf.openfoam_native_artifacts import (
    NativeOpenFoamArtifactRefused,
    assess_native_openfoam_v2_artifact_readiness,
    verify_native_openfoam_v2_artifacts,
    write_native_openfoam_v2_artifacts,
)
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256, topology_constraint_ids


def test_unbound_run_is_explicitly_refused_without_writing_v2_artifacts(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()

    readiness = assess_native_openfoam_v2_artifact_readiness(
        project_yaml=project,
        bundle_dir=bundle_dir,
    )

    assert readiness["ready"] is False
    assert readiness["reasons"] == [
        "missing_native_artifact_binding",
        "response_value_unit_provenance_not_bound",
        "rho_gradient_convention_not_bound",
        "mesh_grid_mapping_not_bound",
        "topology_constraint_values_not_available",
    ]
    output = tmp_path / "native-v2"
    with pytest.raises(NativeOpenFoamArtifactRefused, match="rho_gradient_convention_not_bound"):
        write_native_openfoam_v2_artifacts(
            project_yaml=project,
            bundle_dir=bundle_dir,
            output_dir=output,
        )
    assert not output.exists()


def test_fully_bound_synthetic_run_writes_and_verifies_native_v2_artifacts(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    bundle_dir = _write_bound_synthetic_bundle(tmp_path / "bundle", project)

    artifacts = write_native_openfoam_v2_artifacts(
        project_yaml=project,
        bundle_dir=bundle_dir,
        output_dir=tmp_path / "native-v2",
    )

    primal = read_fixed_grid_primal_summary(artifacts.primal_summary_json)
    sensitivity = read_fixed_grid_sensitivity_summary(artifacts.sensitivity_summary_json)
    assert primal.status == "converged"
    assert primal.response_values[next(iter(primal.response_values))].value == pytest.approx(2.5)
    assert len(sensitivity.gradient_bindings) == 1
    with np.load(artifacts.sensitivity_fields_npz) as fields:
        assert fields["global_cell_ids"].tolist() == [0, 1]
        assert fields["d_force_x_d_rho"].tolist() == pytest.approx([1.25, -0.5])
    verify_native_openfoam_v2_artifacts(
        output_dir=artifacts.output_dir,
        bundle_dir=bundle_dir,
        project_yaml=project,
    )

    source = bundle_dir / "flow_straight" / "optimisation" / "objective" / "0" / "force_xresp_force_x"
    source.write_text("1 3.0 3.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_native_openfoam_v2_artifacts(
            output_dir=artifacts.output_dir,
            bundle_dir=bundle_dir,
            project_yaml=project,
        )


def _write_bound_synthetic_bundle(root: Path, project: Path) -> Path:
    spec = load_problem_spec(project)
    root.mkdir(parents=True)
    case = root / "flow_straight"
    response_metadata = {
        "schema_version": 1,
        "kind": "generated_openfoam_responses",
        "response_mappings": [
            {
                "flow_case_id": "straight",
                "response_id": "force_x",
                "objective_name": "force_x",
                "adjoint_solver_id": "resp_force_x",
            }
        ],
    }
    response_metadata_path = case / "generated_openfoam_responses.json"
    _write_json(response_metadata_path, response_metadata)
    _write_text(case / "log.adjointOptimisationFoam", "End\n")
    _write_text(case / "optimisation" / "objective" / "0" / "force_xresp_force_x", "1 2.5 2.5\n")
    _write_gzip(
        case / "processor0" / "1" / "topologySensresp_force_x.gz",
        _scalar_field("topologySensresp_force_x", "[1 1 -2 0 0 0 0]", [1.25, -0.5]),
    )
    _write_gzip(
        case / "processor0" / "constant" / "polyMesh" / "cellProcAddressing.gz",
        _label_list([0, 1]),
    )
    compilation = {
        "schema_version": 1,
        "kind": "openfoam_case_compilation",
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "execution_ready": spec.migration.execution_ready,
        "flow_case_id": "straight",
        "responses": {"metadata_sha256": _sha256_file(response_metadata_path)},
    }
    compilation_path = case / "openfoam_case_compilation.json"
    _write_json(compilation_path, compilation)
    bundle = {
        "schema_version": 1,
        "kind": "openfoam_case_bundle",
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "execution_ready": spec.migration.execution_ready,
        "status": "compiled",
        "compile_ready": True,
        "flow_cases": {
            "straight": {
                "status": "compiled",
                "case_dir": "flow_straight",
                "compilation_metadata": "flow_straight/openfoam_case_compilation.json",
                "compilation_sha256": _sha256_file(compilation_path),
            }
        },
    }
    bundle_path = root / "openfoam_case_bundle.json"
    _write_json(bundle_path, bundle)
    evidence = {
        "flow_cases": {
            "straight": {
                "case_directory_name": "flow_straight",
                "complete": True,
                "status": "complete",
                "sources": {
                    "response_metadata": _source(case, response_metadata_path),
                    "solver_log": _source(case, case / "log.adjointOptimisationFoam"),
                },
            }
        }
    }
    evidence_path = root / "convergence_evidence.json"
    _write_json(evidence_path, evidence)
    evidence_provenance = {
        "schema_version": 1,
        "kind": "openfoam_convergence_evidence_provenance",
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "execution_ready": spec.migration.execution_ready,
        "evidence_sha256": _sha256_file(evidence_path),
        "bundle_metadata_sha256": _sha256_file(bundle_path),
        "flow_case_ids": ["straight"],
    }
    _write_json(root / "convergence_evidence.json.provenance.json", evidence_provenance)
    qualification = {
        "schema_version": 1,
        "kind": "openfoam_convergence_qualification",
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "execution_ready": spec.migration.execution_ready,
        "status": "pass",
        "qualified": True,
        "flow_cases": {"straight": {"status": "pass", "qualified": True}},
    }
    qualification_path = root / "convergence_qualification.json"
    _write_json(qualification_path, qualification)
    binding = {
        "schema_version": 1,
        "kind": "native_openfoam_v2_artifact_binding",
        "problem_id": spec.problem_id,
        "problem_spec_sha256": problem_spec_sha256(spec),
        "execution_ready": spec.migration.execution_ready,
        "bundle_metadata_sha256": _sha256_file(bundle_path),
        "convergence_evidence_sha256": _sha256_file(evidence_path),
        "convergence_qualification_sha256": _sha256_file(qualification_path),
        "response_value_bindings": [
            {
                "flow_case_id": "straight",
                "response_id": "force_x",
                "units": "N",
                "source": "qualified_solver_force",
            }
        ],
        "gradient_bindings": [
            {
                "flow_case_id": "straight",
                "response_id": "force_x",
                "design_variable_id": "rho",
                "gradient_convention": "d_response_d_rho_cell_integrated",
                "filter_projection_chain_rule": "identity",
                "units": "N",
                "source": "qualified_solver_d_force_d_rho",
                "openfoam_dimensions": "1 1 -2 0 0 0 0",
            }
        ],
        "mesh_binding": {
            "grid_kind": "uniform_cartesian",
            "voxel_size_m": 0.02,
            "ordering": "undecomposed_openfoam_cell_label_ascending",
            "cell_count": 2,
        },
        "topology_constraint_values": [
            {
                "constraint_id": constraint_id,
                "value": 0.0,
                "units": "1",
                "status": "evaluated",
                "source": "qualified_synthetic_topology_evaluator",
            }
            for constraint_id in topology_constraint_ids(spec)
        ],
    }
    _write_json(root / "native_openfoam_v2_artifact_binding.json", binding)
    return root


def _write_project(root: Path) -> Path:
    path = root / "project.yaml"
    path.write_text(
        """schema_version: 2
problem_id: synthetic_native
units: {length: m, time: s, mass: kg}
coordinate_frame:
  id: global
  origin_m: [0, 0, 0]
  basis: {x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1]}
grid: {kind: uniform_cartesian, voxel_size_m: 0.02, padding_m: 0.1}
reference_values: {area_m2: 1.0, length_m: 1.0, moment_center_m: [0, 0, 0]}
geometry_regions:
  - {id: initial, role: initial_design, file: initial.stl}
flow_cases:
  - id: straight
    freestream_velocity_mps: [10, 0, 0]
    fluid: {model: incompressible_newtonian, density_kg_m3: 1.0, dynamic_viscosity_pa_s: 1e-5}
    turbulence: {model: laminar}
    boundary_conditions: {inlet: freestream, outlet: pressure_outlet}
responses:
  - {id: force_x, kind: force, flow_case_id: straight, direction: [1, 0, 0]}
objectives:
  - id: objective
    sense: minimize
    terms: [{coefficient: 1.0, flow_case_id: straight, response_id: force_x}]
constraints:
  - id: force_limit
    relation: <=
    limit: 4.0
    terms: [{coefficient: 1.0, flow_case_id: straight, response_id: force_x}]
topology_policy:
  root_groups: []
  solid_connectivity: {mode: disabled, required_root_group_ids: [], max_components: null, evaluate_eroded: false}
  void_connectivity: {mode: disabled, required_root_group_ids: [], max_components: null, evaluate_eroded: false}
""",
        encoding="utf-8",
    )
    return path


def _scalar_field(name: str, dimensions: str, values: list[float]) -> str:
    return f"""FoamFile
{{
    class volScalarField;
    object {name};
}}
dimensions {dimensions};
internalField nonuniform List<scalar>
{len(values)}
(
{' '.join(map(str, values))}
)
;
"""


def _label_list(values: list[int]) -> str:
    return f"""FoamFile
{{
    class labelList;
    object cellProcAddressing;
}}
{len(values)}
(
{' '.join(map(str, values))}
)
;
"""


def _source(case: Path, path: Path) -> dict[str, object]:
    return {"status": "found", "path": str(path.relative_to(case).as_posix()), "sha256": _sha256_file(path)}


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_gzip(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(text)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
