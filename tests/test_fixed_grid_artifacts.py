from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cfd_sdf.fixed_grid_artifacts import (
    ConstraintKey,
    ResponseKey,
    read_fixed_grid_primal_summary,
    read_fixed_grid_sensitivity_summary,
    validate_primal_summary_against_problem_spec,
    validate_sensitivity_summary_against_problem_spec,
)
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256


VALID_HASH = "a" * 64


def _write_json(tmp_path: Path, data: dict, name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _write_yaml(tmp_path: Path, data: dict, name: str) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _v2_problem_spec() -> dict:
    return {
        "schema_version": 2,
        "problem_id": "generic_wing",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 1.0, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
        },
        "grid": {
            "kind": "uniform_cartesian",
            "voxel_size_m": 0.02,
            "padding_m": 0.1,
        },
        "reference_values": {
            "area_m2": 1.2,
            "length_m": 0.8,
            "moment_center_m": [0.25, 0.0, 0.0],
        },
        "geometry_regions": [
            {"id": "vehicle", "role": "fixed_solid", "file": "geometry/vehicle.stl"},
            {"id": "design_box", "role": "design_domain", "file": "geometry/design_box.stl"},
            {"id": "mount", "role": "root", "file": "geometry/mount.stl"},
        ],
        "flow_cases": [
            {
                "id": "straight",
                "freestream_velocity_mps": [30.0, 0.0, 0.0],
                "fluid": {
                    "model": "incompressible_newtonian",
                    "density_kg_m3": 1.225,
                    "dynamic_viscosity_pa_s": 1.8e-5,
                },
                "turbulence": {"model": "k_omega_sst"},
                "boundary_conditions": {"inlet": "freestream"},
                "motion_profiles": {},
            },
            {
                "id": "yawed",
                "freestream_velocity_mps": [29.5, 5.2, 0.0],
                "fluid": {
                    "model": "incompressible_newtonian",
                    "density_kg_m3": 1.225,
                    "dynamic_viscosity_pa_s": 1.8e-5,
                },
                "turbulence": {"model": "k_omega_sst"},
                "boundary_conditions": {"inlet": "freestream"},
                "motion_profiles": {},
            },
        ],
        "responses": [
            {
                "id": "drag",
                "kind": "force",
                "flow_case_id": "straight",
                "direction": [1.0, 0.0, 0.0],
            },
            {
                "id": "pitch_moment",
                "kind": "moment",
                "flow_case_id": "yawed",
                "direction": [0.0, 1.0, 0.0],
            },
        ],
        "objectives": [
            {
                "id": "multipoint_objective",
                "sense": "minimize",
                "terms": [
                    {"coefficient": 0.7, "flow_case_id": "straight", "response_id": "drag"},
                    {
                        "coefficient": 0.3,
                        "flow_case_id": "yawed",
                        "response_id": "pitch_moment",
                    },
                ],
            }
        ],
        "constraints": [
            {
                "id": "pitch_limit",
                "relation": "<=",
                "limit": 5.0,
                "terms": [
                    {
                        "coefficient": 1.0,
                        "flow_case_id": "yawed",
                        "response_id": "pitch_moment",
                    }
                ],
            }
        ],
        "topology_policy": {
            "root_groups": [{"id": "mounts", "region_ids": ["mount"]}],
            "solid_connectivity": {
                "mode": "required_root_groups",
                "required_root_group_ids": ["mounts"],
                "max_components": 2,
                "evaluate_eroded": False,
            },
            "void_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
                "evaluate_eroded": False,
            },
            "minimum_solid_width_m": None,
            "minimum_void_width_m": None,
            "minimum_gap_m": None,
            "erosion_radius_m": None,
        },
    }


def _load_v2_problem_spec(tmp_path: Path):
    return load_problem_spec(_write_yaml(tmp_path, _v2_problem_spec(), "problem.yaml"))


def _bind_v2_artifact(data: dict, spec) -> dict:
    data["problem_id"] = spec.problem_id
    data["problem_spec_sha256"] = problem_spec_sha256(spec)
    data["execution_ready"] = spec.migration.execution_ready
    return data


def _v2_primal() -> dict:
    return {
        "schema_version": 2,
        "kind": "fixed_grid_primal_summary",
        "problem_id": "generic_wing",
        "problem_spec_sha256": VALID_HASH,
        "execution_ready": True,
        "flow_case_ids": ["straight", "yawed"],
        "status": "converged",
        "response_values": [
            {
                "flow_case_id": "straight",
                "response_id": "drag",
                "value": 0.31,
                "units": "1",
                "status": "converged",
                "source": "openfoam.force_coefficients",
            },
            {
                "flow_case_id": "yawed",
                "response_id": "pitch_moment",
                "value": -0.04,
                "units": "N_m",
                "status": "converged",
                "source": "openfoam.moment",
            },
        ],
        "objective_values": [
            {
                "objective_id": "multipoint_objective",
                "value": 0.205,
                "units": "1",
                "status": "evaluated",
                "source": "weighted_responses",
            }
        ],
        "constraint_values": [
            {
                "scope": "aggregate",
                "constraint_id": "pitch_limit",
                "value": -0.04,
                "units": "N_m",
                "status": "evaluated",
                "source": "pitch_moment",
            },
            {
                "scope": "topology",
                "constraint_id": "solid_connectivity_nominal",
                "value": 0.0,
                "units": "1",
                "status": "evaluated",
                "source": "virtual_diffusion",
            }
        ],
    }


def _v2_sensitivity() -> dict:
    return {
        "schema_version": 2,
        "kind": "fixed_grid_sensitivity_summary",
        "problem_id": "generic_wing",
        "problem_spec_sha256": VALID_HASH,
        "execution_ready": True,
        "flow_case_ids": ["straight", "yawed"],
        "status": "extracted",
        "gradient_bindings": [
            {
                "target_kind": "response",
                "flow_case_id": "straight",
                "response_id": "drag",
                "constraint_id": None,
                "scope": "flow",
                "design_variable_id": "rho",
                "array_name": "d_drag_d_rho",
                "units": "1",
                "status": "extracted",
                "source": "openfoam.toposens_drag",
            },
            {
                "target_kind": "response",
                "flow_case_id": "yawed",
                "response_id": "pitch_moment",
                "objective_id": None,
                "constraint_id": None,
                "scope": "flow",
                "design_variable_id": "rho",
                "array_name": "d_pitch_moment_d_rho",
                "units": "N_m",
                "status": "extracted",
                "source": "openfoam.toposens_pitch",
            },
            {
                "target_kind": "objective",
                "flow_case_id": None,
                "response_id": None,
                "objective_id": "multipoint_objective",
                "constraint_id": None,
                "scope": "aggregate",
                "design_variable_id": "rho",
                "array_name": "d_multipoint_objective_d_rho",
                "units": "1",
                "status": "derived",
                "source": "weighted_response_gradients",
            },
            {
                "target_kind": "constraint",
                "flow_case_id": None,
                "response_id": None,
                "objective_id": None,
                "constraint_id": "pitch_limit",
                "scope": "aggregate",
                "design_variable_id": "rho",
                "array_name": "d_pitch_limit_d_rho",
                "units": "1",
                "status": "derived",
                "source": "weighted_response_gradient",
            },
            {
                "target_kind": "constraint",
                "flow_case_id": None,
                "response_id": None,
                "objective_id": None,
                "constraint_id": "solid_connectivity_nominal",
                "scope": "topology",
                "design_variable_id": "rho",
                "array_name": "d_solid_connectivity_nominal_d_rho",
                "units": "1",
                "status": "evaluated",
                "source": "virtual_diffusion",
            },
        ],
    }


def test_v1_primal_golden_dict_is_normalized_without_rewrite(tmp_path: Path) -> None:
    raw = {
        "schema_version": 1,
        "kind": "fixed_grid_primal_summary",
        "status": "converged",
        "units": {
            "drag_coefficient": "1",
            "downforce_coefficient": "1",
            "objective": "1",
            "efficiency_constraint": "1",
        },
        "drag_coefficient": 0.4,
        "downforce_coefficient": 0.9,
        "objective": -0.9,
        "efficiency_constraint": 0.3,
    }
    path = _write_json(tmp_path, raw, "v1_primal.json")
    before = path.read_bytes()

    summary = read_fixed_grid_primal_summary(path)

    assert summary.problem.problem_id == "legacy_front_wing"
    assert summary.problem.problem_spec_sha256 is None
    assert summary.problem.execution_ready is False
    assert summary.flow_case_ids == ("legacy_default",)
    assert summary.flow_case_id == "legacy_default"
    assert summary.response_values[ResponseKey("legacy_default", "drag")].value == pytest.approx(0.4)
    assert summary.response_values[ResponseKey("legacy_default", "downforce")].value == pytest.approx(0.9)
    assert len(summary.response_values) == 2
    assert summary.objective_values["legacy_objective"].value == pytest.approx(-0.9)
    assert summary.constraint_values[ConstraintKey("aggregate", "efficiency")].value == pytest.approx(0.3)
    assert path.read_bytes() == before


def test_v1_sensitivity_array_metadata_is_normalized(tmp_path: Path) -> None:
    raw = {
        "schema_version": 1,
        "kind": "fixed_grid_sensitivity_summary",
        "status": "extracted",
        "design_variable": "rho",
        "array_metadata": {
            "d_drag_d_rho": {"units": "1", "source": "topOSensas1"},
            "d_efficiency_constraint_d_rho": {"units": "1", "source": "derived"},
            "d_connectivity_nominal_d_rho": {
                "units": "1",
                "source": "virtual diffusion",
                "status": "evaluated",
            },
            "active_design_mask": {"units": "1", "source": "role mask"},
        },
    }
    summary = read_fixed_grid_sensitivity_summary(_write_json(tmp_path, raw, "v1_sensitivity.json"))

    assert summary.problem.execution_ready is False
    assert len(summary.gradient_bindings) == 3
    drag, efficiency, topology = summary.gradient_bindings
    assert (drag.target_kind, drag.scope, drag.flow_case_id, drag.response_id) == (
        "response",
        "flow",
        "legacy_default",
        "drag",
    )
    assert efficiency.constraint_id == "efficiency"
    assert (efficiency.scope, efficiency.flow_case_id) == ("aggregate", None)
    assert (topology.scope, topology.flow_case_id, topology.constraint_id) == (
        "topology",
        None,
        "connectivity_nominal",
    )


def test_v2_primal_response_values_are_keyed_by_flow_and_response(tmp_path: Path) -> None:
    path = _write_json(tmp_path, _v2_primal(), "v2_primal.json")
    before = path.read_bytes()
    summary = read_fixed_grid_primal_summary(path)

    assert summary.problem.problem_id == "generic_wing"
    assert summary.problem.problem_spec_sha256 == VALID_HASH
    assert summary.problem.execution_ready is True
    assert summary.flow_case_ids == ("straight", "yawed")
    assert summary.flow_case_id is None
    assert summary.response_values[ResponseKey("yawed", "pitch_moment")].value == pytest.approx(-0.04)
    assert summary.objective_values["multipoint_objective"].value == pytest.approx(0.205)
    assert summary.constraint_values[ConstraintKey("aggregate", "pitch_limit")].value == pytest.approx(-0.04)
    assert (
        summary.constraint_values[ConstraintKey("topology", "solid_connectivity_nominal")].value
        == pytest.approx(0.0)
    )
    assert path.read_bytes() == before


def test_v2_primal_allows_empty_constraint_values(tmp_path: Path) -> None:
    data = _v2_primal()
    data["constraint_values"] = []

    summary = read_fixed_grid_primal_summary(_write_json(tmp_path, data, "no_constraints.json"))
    assert dict(summary.constraint_values) == {}


@pytest.mark.parametrize("collection", ["response_values", "objective_values"])
def test_v2_primal_requires_response_and_objective_values(tmp_path: Path, collection: str) -> None:
    data = _v2_primal()
    data[collection] = []

    with pytest.raises(ValueError, match=f"{collection} must not be empty"):
        read_fixed_grid_primal_summary(_write_json(tmp_path, data, f"empty_{collection}.json"))


def test_v2_primal_rejects_duplicate_objective_values(tmp_path: Path) -> None:
    data = _v2_primal()
    data["objective_values"].append(dict(data["objective_values"][0]))

    with pytest.raises(ValueError, match="Duplicate objective_id"):
        read_fixed_grid_primal_summary(_write_json(tmp_path, data, "duplicate_objective_values.json"))


def test_v2_primal_rejects_duplicate_constraint_key(tmp_path: Path) -> None:
    data = _v2_primal()
    data["constraint_values"].append(dict(data["constraint_values"][0]))

    with pytest.raises(ValueError, match="Duplicate constraint key"):
        read_fixed_grid_primal_summary(_write_json(tmp_path, data, "duplicate_constraint_key.json"))


def test_v2_primal_allows_same_constraint_id_in_different_scopes(tmp_path: Path) -> None:
    data = _v2_primal()
    data["constraint_values"].append(
        {
            **data["constraint_values"][0],
            "scope": "topology",
        }
    )
    path = _write_json(tmp_path, data, "same_constraint_id_different_scope.json")
    before = path.read_bytes()

    summary = read_fixed_grid_primal_summary(path)

    assert ConstraintKey("aggregate", "pitch_limit") in summary.constraint_values
    assert ConstraintKey("topology", "pitch_limit") in summary.constraint_values
    assert path.read_bytes() == before


@pytest.mark.parametrize("scope", ["flow", "invalid", ""])
def test_v2_primal_rejects_invalid_constraint_scope(tmp_path: Path, scope: str) -> None:
    data = _v2_primal()
    data["constraint_values"][0]["scope"] = scope

    with pytest.raises(ValueError, match="scope"):
        read_fixed_grid_primal_summary(_write_json(tmp_path, data, "invalid_constraint_scope.json"))


def test_v2_primal_requires_constraint_scope(tmp_path: Path) -> None:
    data = _v2_primal()
    data["constraint_values"][0].pop("scope")

    with pytest.raises(ValueError, match="scope"):
        read_fixed_grid_primal_summary(_write_json(tmp_path, data, "missing_constraint_scope.json"))


def test_v2_sensitivity_supports_flow_and_topology_bindings(tmp_path: Path) -> None:
    data = _v2_sensitivity()
    path = _write_json(tmp_path, data, "v2_sensitivity.json")
    before = path.read_bytes()
    summary = read_fixed_grid_sensitivity_summary(path)

    assert summary.flow_case_ids == ("straight", "yawed")
    assert len(summary.gradient_bindings) == 5
    assert {binding.flow_case_id for binding in summary.gradient_bindings[:2]} == {"straight", "yawed"}
    objective = summary.gradient_bindings[2]
    assert (objective.target_kind, objective.scope, objective.objective_id) == (
        "objective",
        "aggregate",
        "multipoint_objective",
    )
    aggregate_constraint = summary.gradient_bindings[3]
    assert (aggregate_constraint.scope, aggregate_constraint.flow_case_id) == ("aggregate", None)
    topology = summary.gradient_bindings[-1]
    assert topology.target_kind == "constraint"
    assert topology.scope == "topology"
    assert topology.flow_case_id is None
    assert topology.constraint_id == "solid_connectivity_nominal"
    assert path.read_bytes() == before


def test_v2_primal_semantics_validate_against_problem_spec(tmp_path: Path) -> None:
    spec = _load_v2_problem_spec(tmp_path)
    path = _write_json(
        tmp_path,
        _bind_v2_artifact(_v2_primal(), spec),
        "bound_v2_primal.json",
    )
    before = path.read_bytes()

    validate_primal_summary_against_problem_spec(read_fixed_grid_primal_summary(path), spec)

    assert path.read_bytes() == before


def test_v2_sensitivity_semantics_validate_against_problem_spec(tmp_path: Path) -> None:
    spec = _load_v2_problem_spec(tmp_path)
    path = _write_json(
        tmp_path,
        _bind_v2_artifact(_v2_sensitivity(), spec),
        "bound_v2_sensitivity.json",
    )
    before = path.read_bytes()

    validate_sensitivity_summary_against_problem_spec(
        read_fixed_grid_sensitivity_summary(path), spec
    )

    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(problem_id="other_problem"), "Problem ID mismatch"),
        (lambda data: data.update(problem_spec_sha256="b" * 64), "hash mismatch"),
        (lambda data: data.update(execution_ready=False), "execution_ready mismatch"),
        (lambda data: data["flow_case_ids"].append("missing_case"), "not declared"),
    ],
)
def test_v2_binding_mismatches_are_rejected(
    tmp_path: Path, mutation, message: str
) -> None:
    spec = _load_v2_problem_spec(tmp_path)
    data = _bind_v2_artifact(_v2_primal(), spec)
    mutation(data)
    summary = read_fixed_grid_primal_summary(
        _write_json(tmp_path, data, "binding_mismatch.json")
    )

    with pytest.raises(ValueError, match=message):
        validate_primal_summary_against_problem_spec(summary, spec)


@pytest.mark.parametrize(
    ("artifact", "mutation", "message"),
    [
        (
            "primal",
            lambda data: data["response_values"][0].update(response_id="unknown_response"),
            "response binding",
        ),
        (
            "primal",
            lambda data: data["objective_values"][0].update(objective_id="unknown_objective"),
            "objective_id",
        ),
        (
            "primal",
            lambda data: data["constraint_values"][0].update(
                constraint_id="unknown_aggregate"
            ),
            "constraint binding",
        ),
        (
            "primal",
            lambda data: data["constraint_values"][1].update(
                constraint_id="unknown_topology"
            ),
            "constraint binding",
        ),
        (
            "sensitivity",
            lambda data: data["gradient_bindings"][0].update(
                response_id="unknown_response"
            ),
            "response binding",
        ),
        (
            "sensitivity",
            lambda data: data["gradient_bindings"][2].update(
                objective_id="unknown_objective"
            ),
            "objective_id",
        ),
        (
            "sensitivity",
            lambda data: data["gradient_bindings"][3].update(
                constraint_id="unknown_aggregate"
            ),
            "aggregate constraint_id",
        ),
        (
            "sensitivity",
            lambda data: data["gradient_bindings"][4].update(
                constraint_id="unknown_topology"
            ),
            "topology constraint_id",
        ),
    ],
)
def test_v2_unknown_semantic_bindings_are_rejected(
    tmp_path: Path, artifact: str, mutation, message: str
) -> None:
    spec = _load_v2_problem_spec(tmp_path)
    data = _v2_primal() if artifact == "primal" else _v2_sensitivity()
    _bind_v2_artifact(data, spec)
    mutation(data)
    if artifact == "primal":
        summary = read_fixed_grid_primal_summary(
            _write_json(tmp_path, data, "unknown_primal_semantic.json")
        )
        validator = validate_primal_summary_against_problem_spec
    else:
        summary = read_fixed_grid_sensitivity_summary(
            _write_json(tmp_path, data, "unknown_sensitivity_semantic.json")
        )
        validator = validate_sensitivity_summary_against_problem_spec

    with pytest.raises(ValueError, match=message):
        validator(summary, spec)


def test_v1_summary_validates_against_migrated_legacy_problem_spec(tmp_path: Path) -> None:
    legacy = {
        "objective": {
            "type": "maximize_downforce_with_efficiency_constraint",
            "efficiency_min": 3.0,
        },
        "operating_point": {
            "velocity_mps": 11.0,
            "density": 1.229,
            "viscosity": 1.73e-5,
        },
    }
    spec = load_problem_spec(_write_yaml(tmp_path, legacy, "legacy_problem.yaml"))
    raw = {
        "schema_version": 1,
        "kind": "fixed_grid_primal_summary",
        "status": "converged",
        "drag_coefficient": 0.4,
        "downforce_coefficient": 0.9,
        "objective": -0.9,
        "efficiency_constraint": 0.3,
    }
    summary = read_fixed_grid_primal_summary(
        _write_json(tmp_path, raw, "legacy_bound_primal.json")
    )

    validate_primal_summary_against_problem_spec(summary, spec)


def test_v1_summary_cannot_bind_to_non_migrated_v2_problem_spec(tmp_path: Path) -> None:
    spec = _load_v2_problem_spec(tmp_path)
    raw = {
        "schema_version": 1,
        "kind": "fixed_grid_primal_summary",
        "status": "converged",
        "drag_coefficient": 0.4,
        "downforce_coefficient": 0.9,
        "objective": -0.9,
        "efficiency_constraint": 0.3,
    }
    summary = read_fixed_grid_primal_summary(
        _write_json(tmp_path, raw, "legacy_unbound_primal.json")
    )

    with pytest.raises(ValueError, match="migrated legacy"):
        validate_primal_summary_against_problem_spec(summary, spec)


def test_v2_duplicate_response_key_is_rejected(tmp_path: Path) -> None:
    data = _v2_primal()
    data["response_values"].append(dict(data["response_values"][0]))

    with pytest.raises(ValueError, match="Duplicate response key"):
        read_fixed_grid_primal_summary(_write_json(tmp_path, data, "duplicate_response.json"))


@pytest.mark.parametrize("duplicate", ["key", "array"])
def test_v2_duplicate_gradient_key_or_array_is_rejected(tmp_path: Path, duplicate: str) -> None:
    data = _v2_sensitivity()
    repeated = dict(data["gradient_bindings"][0])
    if duplicate == "key":
        repeated["array_name"] = "d_drag_repeat_d_rho"
    else:
        repeated["response_id"] = "pitch_moment"
    data["gradient_bindings"].append(repeated)

    with pytest.raises(ValueError, match=f"Duplicate gradient {'key' if duplicate == 'key' else 'array_name'}"):
        read_fixed_grid_sensitivity_summary(_write_json(tmp_path, data, f"duplicate_{duplicate}.json"))


@pytest.mark.parametrize("artifact", ["primal", "sensitivity"])
def test_v2_top_level_flow_case_mismatch_is_rejected(tmp_path: Path, artifact: str) -> None:
    if artifact == "primal":
        data = _v2_primal()
        data["response_values"][0]["flow_case_id"] = "missing_case"
        reader = read_fixed_grid_primal_summary
    else:
        data = _v2_sensitivity()
        data["gradient_bindings"][0]["flow_case_id"] = "missing_case"
        reader = read_fixed_grid_sensitivity_summary

    with pytest.raises(ValueError, match="not present in top-level flow_case_ids"):
        reader(_write_json(tmp_path, data, f"mismatch_{artifact}.json"))


@pytest.mark.parametrize("artifact", ["primal", "sensitivity"])
@pytest.mark.parametrize("flow_case_ids", [[], ["yawed", "yawed"]])
def test_v2_flow_case_ids_must_be_nonempty_and_unique(
    tmp_path: Path, artifact: str, flow_case_ids: list[str]
) -> None:
    if artifact == "primal":
        data = _v2_primal()
        reader = read_fixed_grid_primal_summary
    else:
        data = _v2_sensitivity()
        reader = read_fixed_grid_sensitivity_summary
    data["flow_case_ids"] = flow_case_ids

    with pytest.raises(ValueError, match="must not be empty|Duplicate flow_case_id"):
        reader(_write_json(tmp_path, data, f"bad_flow_set_{artifact}.json"))


@pytest.mark.parametrize(
    ("binding_index", "updates", "message"),
    [
        (0, {"objective_id": "multipoint_objective"}, "response gradients require"),
        (2, {"flow_case_id": "straight"}, "objective gradients require"),
        (3, {"response_id": "drag"}, "constraint gradients require"),
        (4, {"scope": "flow"}, "constraint gradients require"),
    ],
)
def test_v2_gradient_binding_rejects_forbidden_field_combinations(
    tmp_path: Path, binding_index: int, updates: dict, message: str
) -> None:
    data = _v2_sensitivity()
    data["gradient_bindings"][binding_index].update(updates)

    with pytest.raises(ValueError, match=message):
        read_fixed_grid_sensitivity_summary(
            _write_json(tmp_path, data, f"forbidden_binding_{binding_index}.json")
        )


@pytest.mark.parametrize("digest", ["a" * 63, "A" * 64, "z" * 64, "not-a-hash"])
def test_v2_invalid_problem_hash_is_rejected(tmp_path: Path, digest: str) -> None:
    data = _v2_primal()
    data["problem_spec_sha256"] = digest

    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        read_fixed_grid_primal_summary(_write_json(tmp_path, data, "invalid_hash.json"))


def test_v2_topology_constraint_rejects_flow_case_id(tmp_path: Path) -> None:
    data = _v2_sensitivity()
    binding = data["gradient_bindings"][-1]
    binding.update(flow_case_id="yawed")

    with pytest.raises(ValueError, match="constraint gradients require"):
        read_fixed_grid_sensitivity_summary(_write_json(tmp_path, data, "bad_topology.json"))


def test_v2_sensitivity_rejects_empty_gradient_bindings(tmp_path: Path) -> None:
    data = _v2_sensitivity()
    data["gradient_bindings"] = []

    with pytest.raises(ValueError, match="gradient_bindings must not be empty"):
        read_fixed_grid_sensitivity_summary(_write_json(tmp_path, data, "empty_gradients.json"))


def test_v1_sensitivity_rejects_missing_gradient_arrays(tmp_path: Path) -> None:
    data = {
        "schema_version": 1,
        "kind": "fixed_grid_sensitivity_summary",
        "status": "not_extracted",
        "array_metadata": {"active_design_mask": {"units": "1", "source": "role mask"}},
    }

    with pytest.raises(ValueError, match=r"at least one d_\* gradient array"):
        read_fixed_grid_sensitivity_summary(_write_json(tmp_path, data, "v1_no_gradients.json"))
