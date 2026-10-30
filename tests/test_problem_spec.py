from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from cfd_sdf.config import load_project
from cfd_sdf.problem_spec import (
    canonical_uniform_cartesian_cell_grid,
    canonical_problem_spec_json,
    load_problem_spec,
    problem_spec_sha256,
    problem_spec_to_dict,
    topology_constraint_ids,
    write_problem_spec_snapshot,
)


def _v2_data() -> dict:
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
            {"id": "vehicle", "role": "fixed_solid", "file": "geometry/vehicle.STL"},
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
                "boundary_conditions": {"inlet": "freestream", "ground": "moving_wall"},
                "motion_profiles": {
                    "moving_ground": {"kind": "translation", "velocity_mps": [30.0, 0.0, 0.0]}
                },
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
                "boundary_conditions": {"inlet": "freestream", "ground": "moving_wall"},
                "motion_profiles": {},
            },
        ],
        "responses": [
            {
                "id": "rotated_force",
                "kind": "force",
                "flow_case_id": "straight",
                "direction": [0.70710678, 0.70710678, 0.0],
            },
            {
                "id": "pitch_moment",
                "kind": "moment",
                "flow_case_id": "yawed",
                "direction": [0.0, 1.0, 0.0],
            },
            {
                "id": "duct_loss",
                "kind": "pressure_loss",
                "flow_case_id": "straight",
                "options": {"from_boundary_id": "inlet", "to_boundary_id": "outlet"},
            },
            {
                "id": "outlet_flow",
                "kind": "flow_rate",
                "flow_case_id": "straight",
                "options": {"boundary_id": "outlet"},
            },
            {
                "id": "custom_metric",
                "kind": "plugin",
                "flow_case_id": "yawed",
                "options": {"plugin_id": "wake_metric", "parameters": {"radius_m": 0.1}},
            },
        ],
        "objectives": [
            {
                "id": "multipoint_objective",
                "sense": "minimize",
                "terms": [
                    {
                        "coefficient": 0.7,
                        "flow_case_id": "straight",
                        "response_id": "rotated_force",
                    },
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
                "evaluate_eroded": True,
            },
            "void_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
                "evaluate_eroded": False,
            },
            "minimum_solid_width_m": 0.01,
            "minimum_void_width_m": 0.012,
            "minimum_gap_m": 0.008,
            "erosion_radius_m": 0.004,
        },
    }


def _write_yaml(tmp_path: Path, data: dict, name: str = "problem.yaml") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_load_v2_two_cases_rotated_force_moment_and_weighted_terms(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_yaml(tmp_path, _v2_data()))

    assert spec.problem_id == "generic_wing"
    assert [region.role for region in spec.geometry_regions] == [
        "fixed_solid",
        "design_domain",
        "root",
    ]
    assert [case.id for case in spec.flow_cases] == ["straight", "yawed"]
    assert spec.responses[0].direction == pytest.approx((0.70710678, 0.70710678, 0.0))
    assert spec.responses[1].kind == "moment"
    assert spec.responses[1].flow_case_id == "yawed"
    assert [term.coefficient for term in spec.objectives[0].terms] == pytest.approx([0.7, 0.3])
    assert spec.constraints[0].relation == "<="
    assert spec.constraints[0].terms[0].response_id == "pitch_moment"
    assert spec.topology_policy.root_groups[0].region_ids == ("mount",)
    assert spec.topology_policy.solid_connectivity.max_components == 2
    assert spec.migration.migrated is False
    assert spec.migration.execution_ready is True


def test_all_response_kinds_and_motion_profiles_are_canonical(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_yaml(tmp_path, _v2_data()))
    content = problem_spec_to_dict(spec)

    assert [response.kind for response in spec.responses] == [
        "force",
        "moment",
        "pressure_loss",
        "flow_rate",
        "plugin",
    ]
    assert spec.responses[2].direction is None
    assert spec.responses[2].options["from_boundary_id"] == "inlet"
    assert spec.responses[4].options["parameters"]["radius_m"] == pytest.approx(0.1)
    assert spec.flow_cases[0].motion_profiles["moving_ground"]["kind"] == "translation"
    assert spec.flow_cases[1].motion_profiles == {}
    assert content["responses"][2]["direction"] is None
    assert content["responses"][4]["options"]["plugin_id"] == "wake_metric"
    assert content["flow_cases"][0]["motion_profiles"]["moving_ground"]["velocity_mps"] == [
        30.0,
        0.0,
        0.0,
    ]


def test_convergence_criteria_defaults_are_explicit_and_canonical(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_yaml(tmp_path, _v2_data()))
    criteria = problem_spec_to_dict(spec)["flow_cases"][0]["convergence_criteria"]

    assert criteria == {
        "primal_final_residual_max": 1.0e-6,
        "normalized_mass_imbalance_max": 1.0e-4,
        "response_stationarity_window": 20,
        "response_relative_range_max": 1.0e-3,
        "adjoint_final_residual_max": 1.0e-6,
    }


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"extra": 1}, "unknown keys"),
        ({"primal_final_residual_max": 0}, "must be positive"),
        ({"primal_final_residual_max": "1e-6"}, "must be a number"),
        ({"adjoint_final_residual_max": 1.1}, "must be at most 1"),
        ({"normalized_mass_imbalance_max": -1}, "must be nonnegative"),
        ({"response_relative_range_max": 1.1}, "must be at most 1"),
        ({"response_stationarity_window": True}, "must be an integer"),
        ({"response_stationarity_window": 1}, "must be between"),
        (None, "must be a mapping"),
    ],
)
def test_convergence_criteria_strict_validation(
    tmp_path: Path, updates: dict, message: str
) -> None:
    data = _v2_data()
    data["flow_cases"][0]["convergence_criteria"] = updates

    with pytest.raises(ValueError, match=message):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_custom_convergence_criteria_change_canonical_hash(tmp_path: Path) -> None:
    baseline = load_problem_spec(_write_yaml(tmp_path, _v2_data(), "baseline.yaml"))
    changed_data = _v2_data()
    changed_data["flow_cases"][0]["convergence_criteria"] = {
        "primal_final_residual_max": 2.0e-6,
        "response_stationarity_window": 30,
    }
    changed = load_problem_spec(_write_yaml(tmp_path, changed_data, "changed.yaml"))

    assert problem_spec_sha256(changed) != problem_spec_sha256(baseline)
    criteria = problem_spec_to_dict(changed)["flow_cases"][0]["convergence_criteria"]
    assert criteria["primal_final_residual_max"] == pytest.approx(2.0e-6)
    assert criteria["response_stationarity_window"] == 30
    assert criteria["adjoint_final_residual_max"] == pytest.approx(1.0e-6)


@pytest.mark.parametrize(
    ("motion_profiles", "message"),
    [
        ([], "motion_profiles must be a mapping"),
        ({"Bad-Key": {}}, "must match"),
        ({"moving_ground": []}, "moving_ground must be a mapping"),
    ],
)
def test_motion_profiles_are_typed_immutable_mappings(
    tmp_path: Path, motion_profiles, message: str
) -> None:
    data = _v2_data()
    data["flow_cases"][0]["motion_profiles"] = motion_profiles

    with pytest.raises(ValueError, match=message):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_motion_profiles_and_plugin_options_are_deeply_immutable(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_yaml(tmp_path, _v2_data()))

    with pytest.raises(TypeError):
        spec.flow_cases[0].motion_profiles["moving_ground"]["kind"] = "rotation"
    with pytest.raises(TypeError):
        spec.responses[4].options["parameters"]["radius_m"] = 0.2


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            {"id": "bad", "kind": "force", "flow_case_id": "straight", "options": {}},
            "direction must contain exactly three",
        ),
        (
            {
                "id": "bad",
                "kind": "pressure_loss",
                "flow_case_id": "straight",
                "direction": [1, 0, 0],
                "options": {"from_boundary_id": "inlet", "to_boundary_id": "outlet"},
            },
            "direction is only allowed",
        ),
        (
            {
                "id": "bad",
                "kind": "pressure_loss",
                "flow_case_id": "straight",
                "options": {"from_boundary_id": "inlet"},
            },
            "to_boundary_id must be a non-empty string",
        ),
        (
            {
                "id": "bad",
                "kind": "pressure_loss",
                "flow_case_id": "straight",
                "options": {"from_boundary_id": "inlet", "to_boundary_id": "inlet"},
            },
            "endpoints must be different",
        ),
        (
            {"id": "bad", "kind": "flow_rate", "flow_case_id": "straight", "options": {}},
            "boundary_id must be a non-empty string",
        ),
        (
            {"id": "bad", "kind": "plugin", "flow_case_id": "straight", "options": {}},
            "plugin_id must be a non-empty string",
        ),
        (
            {"id": "bad", "kind": "unknown", "flow_case_id": "straight", "options": {}},
            "kind must be force",
        ),
    ],
)
def test_response_kind_required_fields_are_enforced(
    tmp_path: Path, response: dict, message: str
) -> None:
    data = _v2_data()
    data["responses"] = [response]
    data["objectives"][0]["terms"] = [
        {"coefficient": 1.0, "flow_case_id": "straight", "response_id": "bad"}
    ]
    data["constraints"] = []

    with pytest.raises(ValueError, match=message):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize("options", [[], "plugin", None])
def test_response_options_must_be_mapping(tmp_path: Path, options) -> None:
    data = _v2_data()
    data["responses"][0]["options"] = options

    with pytest.raises(ValueError, match="options must be a mapping"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    ("response_index", "option_key"),
    [(2, "from_boundary_id"), (2, "to_boundary_id"), (3, "boundary_id"), (4, "plugin_id")],
)
def test_response_required_option_ids_use_stable_id_contract(
    tmp_path: Path, response_index: int, option_key: str
) -> None:
    data = _v2_data()
    data["responses"][response_index]["options"][option_key] = "Bad-ID"

    with pytest.raises(ValueError, match="must match"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize("role", ["fixed_solid", "initial_design", "design_domain", "forbidden_region", "root"])
def test_geometry_region_roles_are_supported_without_file_io(tmp_path: Path, role: str) -> None:
    data = _v2_data()
    data["geometry_regions"] = [
        {"id": "region", "role": role, "file": "does/not/exist.stl"},
        {"id": "domain", "role": "design_domain", "file": "also/missing.stl"},
        {"id": "mount", "role": "root", "file": "also/missing_mount.stl"},
    ]

    spec = load_problem_spec(_write_yaml(tmp_path, data))
    assert spec.geometry_regions[0].role == role
    assert spec.geometry_regions[0].file == Path("does/not/exist.stl")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda region: region.update(role="wall"), "role must be one of"),
        (lambda region: region.update(file="geometry/vehicle.obj"), r"\.stl extension"),
        (lambda region: region.update(file=""), "non-empty path"),
    ],
)
def test_geometry_region_role_and_stl_path_are_validated(
    tmp_path: Path, mutation, message: str
) -> None:
    data = _v2_data()
    mutation(data["geometry_regions"][0])

    with pytest.raises(ValueError, match=message):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_duplicate_geometry_region_ids_are_rejected(tmp_path: Path) -> None:
    data = _v2_data()
    data["geometry_regions"][1]["id"] = data["geometry_regions"][0]["id"]

    with pytest.raises(ValueError, match="Duplicate geometry region id"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_v2_geometry_absolute_path_is_rejected(tmp_path: Path) -> None:
    data = _v2_data()
    data["geometry_regions"][0]["file"] = str((tmp_path / "vehicle.stl").resolve())

    with pytest.raises(ValueError, match="relative path for a portable contract"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_relative_geometry_paths_hash_identically_across_config_directories(tmp_path: Path) -> None:
    first = load_problem_spec(_write_yaml(tmp_path / "pc_a", _v2_data()))
    second = load_problem_spec(_write_yaml(tmp_path / "pc_b", _v2_data()))

    assert first.path != second.path
    assert problem_spec_sha256(first) == problem_spec_sha256(second)
    assert problem_spec_to_dict(first)["geometry_regions"][0]["file"] == "geometry/vehicle.STL"


def test_missing_design_domain_is_schema_valid_but_not_execution_ready(tmp_path: Path) -> None:
    data = _v2_data()
    data["geometry_regions"] = [
        region for region in data["geometry_regions"] if region["role"] != "design_domain"
    ]

    spec = load_problem_spec(_write_yaml(tmp_path, data))
    assert spec.migration.execution_ready is False


@pytest.mark.parametrize(
    ("mode", "required_ids", "max_components"),
    [
        ("disabled", [], None),
        ("single_component", [], 1),
        ("root_connected", ["mounts"], None),
        ("required_root_groups", ["mounts"], 2),
        ("bounded_component_count", [], 3),
    ],
)
def test_connectivity_modes_are_typed_and_independent(
    tmp_path: Path, mode: str, required_ids: list[str], max_components: int | None
) -> None:
    data = _v2_data()
    data["topology_policy"]["void_connectivity"] = {
        "mode": mode,
        "required_root_group_ids": required_ids,
        "max_components": max_components,
        "evaluate_eroded": mode != "disabled",
    }

    policy = load_problem_spec(_write_yaml(tmp_path, data)).topology_policy
    assert policy.void_connectivity.mode == mode
    assert policy.void_connectivity.required_root_group_ids == tuple(required_ids)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"mode": "unknown"}, "mode must be one of"),
        ({"mode": "disabled", "required_root_group_ids": ["mounts"]}, "disabled mode forbids"),
        ({"mode": "disabled", "max_components": 2}, "disabled mode forbids"),
        ({"mode": "single_component", "required_root_group_ids": ["mounts"]}, "single_component mode"),
        ({"mode": "single_component", "max_components": 2}, "single_component mode"),
        ({"mode": "root_connected", "required_root_group_ids": []}, "requires required_root_group_ids"),
        ({"mode": "required_root_groups", "required_root_group_ids": []}, "requires required_root_group_ids"),
        ({"mode": "bounded_component_count", "max_components": None}, "requires max_components"),
    ],
)
def test_connectivity_mode_conditions_are_enforced(
    tmp_path: Path, updates: dict, message: str
) -> None:
    data = _v2_data()
    data["topology_policy"]["solid_connectivity"].update(updates)

    with pytest.raises(ValueError, match=message):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize("max_components", [True, 0, -1, 1.5])
def test_max_components_requires_positive_non_bool_integer(
    tmp_path: Path, max_components
) -> None:
    data = _v2_data()
    data["topology_policy"]["solid_connectivity"]["max_components"] = max_components

    with pytest.raises(ValueError, match="positive integer or null"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize("evaluate_eroded", [0, 1, "true", None])
def test_evaluate_eroded_requires_strict_boolean(tmp_path: Path, evaluate_eroded) -> None:
    data = _v2_data()
    data["topology_policy"]["solid_connectivity"]["evaluate_eroded"] = evaluate_eroded

    with pytest.raises(ValueError, match="must be a boolean"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_disabled_connectivity_rejects_eroded_evaluation(tmp_path: Path) -> None:
    data = _v2_data()
    data["topology_policy"]["void_connectivity"]["evaluate_eroded"] = True

    with pytest.raises(ValueError, match="disabled mode requires evaluate_eroded=false"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_eroded_evaluation_requires_erosion_radius(tmp_path: Path) -> None:
    data = _v2_data()
    data["topology_policy"]["erosion_radius_m"] = None

    with pytest.raises(ValueError, match="erosion_radius_m is required"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["topology_policy"]["root_groups"][0].update(region_ids=[]), "must not be empty"),
        (
            lambda data: data["topology_policy"]["root_groups"][0].update(region_ids=["missing"]),
            "unknown geometry region",
        ),
        (
            lambda data: data["topology_policy"]["root_groups"][0].update(region_ids=["vehicle"]),
            "must have role='root'",
        ),
        (
            lambda data: data["topology_policy"]["root_groups"][0].update(region_ids=["mount", "mount"]),
            "Duplicate ID",
        ),
        (
            lambda data: data["topology_policy"]["solid_connectivity"].update(
                required_root_group_ids=["missing_group"]
            ),
            "unknown root group",
        ),
        (
            lambda data: data["topology_policy"]["solid_connectivity"].update(
                required_root_group_ids=["mounts", "mounts"]
            ),
            "Duplicate ID",
        ),
    ],
)
def test_root_group_references_and_duplicates_are_validated(
    tmp_path: Path, mutation, message: str
) -> None:
    data = _v2_data()
    mutation(data)

    with pytest.raises(ValueError, match=message):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_duplicate_root_group_ids_are_rejected(tmp_path: Path) -> None:
    data = _v2_data()
    data["topology_policy"]["root_groups"].append(
        {"id": "mounts", "region_ids": ["mount"]}
    )

    with pytest.raises(ValueError, match="Duplicate root group id"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    "field",
    ["minimum_solid_width_m", "minimum_void_width_m", "minimum_gap_m", "erosion_radius_m"],
)
@pytest.mark.parametrize("value", [0.0, -0.1])
def test_topology_dimensions_must_be_positive_when_set(
    tmp_path: Path, field: str, value: float
) -> None:
    data = _v2_data()
    data["topology_policy"][field] = value

    with pytest.raises(ValueError, match="must be positive"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_topology_dimensions_may_be_null(tmp_path: Path) -> None:
    data = _v2_data()
    for field in (
        "minimum_solid_width_m",
        "minimum_void_width_m",
        "minimum_gap_m",
        "erosion_radius_m",
    ):
        data["topology_policy"][field] = None
    data["topology_policy"]["solid_connectivity"]["evaluate_eroded"] = False

    policy = load_problem_spec(_write_yaml(tmp_path, data)).topology_policy
    assert policy.minimum_solid_width_m is None
    assert policy.minimum_void_width_m is None
    assert policy.minimum_gap_m is None
    assert policy.erosion_radius_m is None


def test_topology_constraint_ids_have_stable_exact_order(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_yaml(tmp_path, _v2_data()))

    assert topology_constraint_ids(spec) == (
        "solid_connectivity_nominal",
        "solid_connectivity_eroded",
        "minimum_solid_width",
        "minimum_void_width",
        "minimum_gap",
    )


def test_disabled_null_topology_has_no_derived_constraint_ids(tmp_path: Path) -> None:
    data = _v2_data()
    for name in ("solid_connectivity", "void_connectivity"):
        data["topology_policy"][name] = {
            "mode": "disabled",
            "required_root_group_ids": [],
            "max_components": None,
            "evaluate_eroded": False,
        }
    for name in ("minimum_solid_width_m", "minimum_void_width_m", "minimum_gap_m"):
        data["topology_policy"][name] = None

    spec = load_problem_spec(_write_yaml(tmp_path, data))
    assert topology_constraint_ids(spec) == ()


def test_topology_constraint_ids_are_derived_without_changing_canonical_hash(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_yaml(tmp_path, _v2_data()))
    digest_before = problem_spec_sha256(spec)

    assert topology_constraint_ids(spec)
    assert "topology_constraint_ids" not in problem_spec_to_dict(spec)
    assert problem_spec_sha256(spec) == digest_before


@pytest.mark.parametrize("value", [None, [], "disabled"])
def test_topology_policy_is_required_mapping(tmp_path: Path, value) -> None:
    data = _v2_data()
    if value is None:
        data.pop("topology_policy")
    else:
        data["topology_policy"] = value

    with pytest.raises(ValueError, match="topology_policy must be a mapping"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_v2_execution_ready_requires_references_and_every_case_bc(tmp_path: Path) -> None:
    missing_references = _v2_data()
    missing_references.pop("reference_values")
    assert load_problem_spec(_write_yaml(tmp_path, missing_references, "no_refs.yaml")).migration.execution_ready is False

    missing_bc = _v2_data()
    missing_bc["flow_cases"][1].pop("boundary_conditions")
    assert load_problem_spec(_write_yaml(tmp_path, missing_bc, "no_bc.yaml")).migration.execution_ready is False

    empty_references = _v2_data()
    empty_references["reference_values"] = {}
    assert load_problem_spec(_write_yaml(tmp_path, empty_references, "empty_refs.yaml")).migration.execution_ready is False

    partial_references = _v2_data()
    partial_references["reference_values"].pop("area_m2")
    assert load_problem_spec(_write_yaml(tmp_path, partial_references, "partial_refs.yaml")).migration.execution_ready is False

    empty_bc = _v2_data()
    empty_bc["flow_cases"][0]["boundary_conditions"] = {}
    assert load_problem_spec(_write_yaml(tmp_path, empty_bc, "empty_bc.yaml")).migration.execution_ready is False

    unsupported_grid = _v2_data()
    unsupported_grid["grid"]["kind"] = "octree_amr"
    assert load_problem_spec(_write_yaml(tmp_path, unsupported_grid, "octree.yaml")).migration.execution_ready is False

    missing_turbulence = _v2_data()
    missing_turbulence["flow_cases"][0].pop("turbulence")
    assert (
        load_problem_spec(_write_yaml(tmp_path, missing_turbulence, "no_turbulence.yaml")).migration.execution_ready
        is False
    )


def test_octree_grid_and_options_roundtrip_but_are_not_execution_ready(tmp_path: Path) -> None:
    data = _v2_data()
    data["grid"].update(kind="octree_amr", max_level=5, refinement={"wake": 3})

    spec = load_problem_spec(_write_yaml(tmp_path, data))
    content = problem_spec_to_dict(spec)

    assert spec.grid.kind == "octree_amr"
    assert spec.grid.options["max_level"] == 5
    assert content["grid"]["refinement"]["wake"] == 3
    assert spec.migration.execution_ready is False


@pytest.mark.parametrize("kind", ["cartesian", "unstructured", "OCTREE_AMR"])
def test_unknown_grid_kind_is_rejected(tmp_path: Path, kind: str) -> None:
    data = _v2_data()
    data["grid"]["kind"] = kind

    with pytest.raises(ValueError, match="grid.kind must be"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_unknown_v2_top_level_keys_are_rejected(tmp_path: Path) -> None:
    data = _v2_data()
    data["problem_identifer"] = "typo"

    with pytest.raises(ValueError, match=r"unknown keys.*problem_identifer"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data["units"].update(lenght="m"),
        lambda data: data["coordinate_frame"].update(orign_m=[0, 0, 0]),
        lambda data: data["coordinate_frame"]["basis"].update(w=[0, 0, 1]),
        lambda data: data["reference_values"].update(area_m_2=1.0),
        lambda data: data["geometry_regions"][0].update(path="geometry/vehicle.stl"),
        lambda data: data["flow_cases"][0].update(freestream_velocity=[1, 0, 0]),
        lambda data: data["flow_cases"][0]["fluid"].update(rho=1.2),
        lambda data: data["responses"][0].update(response_options={}),
        lambda data: data["objectives"][0].update(direction="minimize"),
        lambda data: data["constraints"][0].update(bound=5.0),
        lambda data: data["objectives"][0]["terms"][0].update(weight=0.7),
        lambda data: data["topology_policy"].update(min_gap_m=0.01),
        lambda data: data["topology_policy"]["root_groups"][0].update(regions=["mount"]),
        lambda data: data["topology_policy"]["solid_connectivity"].update(eroded=True),
    ],
)
def test_structured_v2_mappings_reject_unknown_keys(tmp_path: Path, mutation) -> None:
    data = _v2_data()
    mutation(data)

    with pytest.raises(ValueError, match="unknown keys"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_legacy_unknown_keys_remain_compatible(tmp_path: Path) -> None:
    legacy = {
        "legacy_extension": {"vendor": "kept_outside_canonical_contract"},
        "objective": {"type": "maximize_downforce_with_efficiency_constraint"},
        "operating_point": {"velocity_mps": 11.0, "density": 1.229, "viscosity": 1.73e-5},
    }

    spec = load_problem_spec(_write_yaml(tmp_path, legacy, "legacy_extension.yaml"))
    assert spec.problem_id == "legacy_front_wing"
    assert spec.migration.execution_ready is False


@pytest.mark.parametrize("boundary_conditions", [[], "inlet", 4])
def test_boundary_conditions_must_be_mapping_or_null(tmp_path: Path, boundary_conditions) -> None:
    data = _v2_data()
    data["flow_cases"][0]["boundary_conditions"] = boundary_conditions

    with pytest.raises(ValueError, match="boundary_conditions must be a mapping or null"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize("collection", ["flow_cases", "responses", "objectives"])
def test_required_collections_must_not_be_empty(tmp_path: Path, collection: str) -> None:
    data = _v2_data()
    data[collection] = []

    with pytest.raises(ValueError, match=f"{collection} must not be empty"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_constraints_may_be_empty(tmp_path: Path) -> None:
    data = _v2_data()
    data["constraints"] = []

    assert load_problem_spec(_write_yaml(tmp_path, data)).constraints == ()


@pytest.mark.parametrize("collection", ["flow_cases", "responses", "objectives", "constraints"])
def test_duplicate_ids_are_rejected(tmp_path: Path, collection: str) -> None:
    data = _v2_data()
    data[collection].append(deepcopy(data[collection][0]))

    with pytest.raises(ValueError, match="Duplicate .* id"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["responses"][0].update(flow_case_id="missing_case"), "unknown flow_case_id"),
        (
            lambda data: data["objectives"][0]["terms"][0].update(flow_case_id="missing_case"),
            "unknown flow_case_id",
        ),
        (
            lambda data: data["objectives"][0]["terms"][0].update(response_id="missing_response"),
            "unknown response_id",
        ),
    ],
)
def test_unknown_flow_and_response_ids_are_rejected(tmp_path: Path, mutation, message: str) -> None:
    data = _v2_data()
    mutation(data)

    with pytest.raises(ValueError, match=message):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data["coordinate_frame"]["basis"].update(x=[0.0, 0.0, 0.0]),
        lambda data: data["flow_cases"][0].update(freestream_velocity_mps=[0.0, 0.0, 0.0]),
        lambda data: data["responses"][0].update(direction=[0.0, 0.0, 0.0]),
    ],
)
def test_required_vectors_must_be_nonzero(tmp_path: Path, mutation) -> None:
    data = _v2_data()
    mutation(data)

    with pytest.raises(ValueError, match="must be nonzero"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize(
    ("basis", "message"),
    [
        ({"x": [2.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}, "unit vector"),
        ({"x": [1.0, 0.0, 0.0], "y": [1.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}, "unit vector"),
        (
            {
                "x": [1.0, 0.0, 0.0],
                "y": [0.70710678, 0.70710678, 0.0],
                "z": [0.0, 0.0, 1.0],
            },
            "mutually orthogonal",
        ),
        ({"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, -1.0]}, "right-handed"),
    ],
)
def test_coordinate_basis_must_be_orthonormal_and_right_handed(
    tmp_path: Path, basis: dict, message: str
) -> None:
    data = _v2_data()
    data["coordinate_frame"]["basis"] = basis

    with pytest.raises(ValueError, match=message):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_rotated_orthonormal_right_handed_basis_is_accepted(tmp_path: Path) -> None:
    data = _v2_data()
    data["coordinate_frame"]["basis"] = {
        "x": [0.70710678, 0.70710678, 0.0],
        "y": [-0.70710678, 0.70710678, 0.0],
        "z": [0.0, 0.0, 1.0],
    }

    spec = load_problem_spec(_write_yaml(tmp_path, data))
    assert spec.coordinate_frame.basis.x == pytest.approx((0.70710678, 0.70710678, 0.0))


@pytest.mark.parametrize("property_name", ["density_kg_m3", "dynamic_viscosity_pa_s"])
@pytest.mark.parametrize("value", [0.0, -1.0])
def test_density_and_viscosity_must_be_positive(tmp_path: Path, property_name: str, value: float) -> None:
    data = _v2_data()
    data["flow_cases"][0]["fluid"][property_name] = value

    with pytest.raises(ValueError, match="must be positive"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize("collection", ["objectives", "constraints"])
def test_weighted_definition_rejects_all_zero_coefficients(tmp_path: Path, collection: str) -> None:
    data = _v2_data()
    for term in data[collection][0]["terms"]:
        term["coefficient"] = 0.0

    with pytest.raises(ValueError, match="at least one nonzero coefficient"):
        load_problem_spec(_write_yaml(tmp_path, data))


@pytest.mark.parametrize("bad_id", ["UpperCase", "starts-with-dash", "2starts_with_digit", "a" * 65])
def test_ids_follow_stable_contract(tmp_path: Path, bad_id: str) -> None:
    data = _v2_data()
    data["responses"][0]["id"] = bad_id

    with pytest.raises(ValueError, match="must match"):
        load_problem_spec(_write_yaml(tmp_path, data))


def test_legacy_migration_is_not_execution_ready_and_invents_no_refs_or_bc(tmp_path: Path) -> None:
    legacy = {
        "grid": {"voxel_size_m": 0.04, "padding_m": 0.12},
        "objective": {
            "type": "maximize_downforce_with_efficiency_constraint",
            "efficiency_min": 3.0,
        },
        "operating_point": {"velocity_mps": 11.0, "density": 1.229, "viscosity": 1.73e-5},
    }

    spec = load_problem_spec(_write_yaml(tmp_path, legacy, "legacy.yaml"))

    assert spec.flow_cases[0].id == "legacy_default"
    assert [response.id for response in spec.responses] == ["drag", "downforce"]
    assert spec.constraints[0].id == "efficiency"
    assert spec.constraints[0].terms[1].coefficient == pytest.approx(-3.0)
    assert spec.reference_values is None
    assert spec.flow_cases[0].boundary_conditions is None
    assert spec.flow_cases[0].motion_profiles == {}
    assert spec.responses[0].options == {}
    assert spec.topology_policy.root_groups == ()
    assert spec.topology_policy.solid_connectivity.mode == "disabled"
    assert spec.topology_policy.void_connectivity.evaluate_eroded is False
    assert spec.migration.migrated is True
    assert spec.migration.execution_ready is False


def test_legacy_migration_optionally_bridges_declared_reference_values(tmp_path: Path) -> None:
    """A legacy v1 project may optionally declare reference_values so the body-fitted
    OpenFOAM path (which only ever reads config.problem_spec, never a native v2 spec)
    can compute real forceCoeffs instead of defaulting Aref/lRef to 1."""

    legacy = {
        "grid": {"voxel_size_m": 0.04, "padding_m": 0.12},
        "objective": {
            "type": "maximize_downforce_with_efficiency_constraint",
            "efficiency_min": 3.0,
        },
        "operating_point": {"velocity_mps": 11.0, "density": 1.229, "viscosity": 1.73e-5},
        "reference_values": {"area_m2": 0.35, "length_m": 1.6},
    }

    spec = load_problem_spec(_write_yaml(tmp_path, legacy, "legacy.yaml"))

    assert spec.reference_values is not None
    assert spec.reference_values.area_m2 == 0.35
    assert spec.reference_values.length_m == 1.6
    # Declaring reference_values does not by itself make legacy migration execution-ready;
    # boundary conditions and turbulence are still unspecified.
    assert spec.migration.execution_ready is False


def test_legacy_geometry_and_stl_roots_migrate_to_canonical_regions(tmp_path: Path) -> None:
    legacy = {
        "geometry": {
            "fixed_solids": [{"id": "body", "file": "geometry/body.stl"}],
            "design_geometry": [{"id": "seed", "file": "geometry/seed.stl"}],
            "design_domains": [{"id": "domain", "file": "geometry/domain.stl"}],
            "forbidden_regions": [{"id": "keepout", "file": "geometry/keepout.stl"}],
        },
        "roots": [
            {"id": "mount", "type": "stl", "file": "geometry/mount.STL"},
            {"id": "analytic_root", "type": "sphere", "center_m": [0, 0, 0]},
        ],
    }

    spec = load_problem_spec(_write_yaml(tmp_path, legacy, "legacy_geometry.yaml"))

    assert [(region.id, region.role) for region in spec.geometry_regions] == [
        ("body", "fixed_solid"),
        ("seed", "initial_design"),
        ("domain", "design_domain"),
        ("keepout", "forbidden_region"),
        ("mount", "root"),
    ]
    assert spec.geometry_regions[-1].file == Path("geometry/mount.STL")
    assert any("analytic or malformed legacy root" in note for note in spec.migration.notes)
    assert spec.migration.execution_ready is False
    assert problem_spec_to_dict(spec)["geometry_regions"][2]["file"] == "geometry/domain.stl"


def test_legacy_load_project_remains_compatible_and_exposes_problem_spec(tmp_path: Path) -> None:
    legacy = {
        "geometry": {
            "design_geometry": [{"id": "seed", "file": "geometry/seed.stl"}],
        },
        "grid": {"voxel_size_m": 0.04, "padding_m": 0.12, "band_width_m": 0.2},
        "objective": {
            "type": "maximize_downforce_with_efficiency_constraint",
            "efficiency_min": 4.0,
        },
        "operating_point": {"velocity_mps": 20.0, "density": 1.2, "viscosity": 1.8e-5},
        "output_dir": "runs/compatibility",
    }

    config = load_project(_write_yaml(tmp_path, legacy, "project.yaml"))

    assert config.design_geometry[0].id == "seed"
    assert config.grid.voxel_size_m == pytest.approx(0.04)
    assert config.objective.efficiency_min == pytest.approx(4.0)
    assert config.operating_point.velocity_mps == pytest.approx(20.0)
    assert config.problem_spec is not None
    assert config.problem_spec.flow_cases[0].id == "legacy_default"


def test_legacy_load_project_rejects_v2_without_projection(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, _v2_data())

    with pytest.raises(ValueError, match=r"use load_problem_spec\(\)"):
        load_project(path)


def test_canonical_hash_ignores_absolute_source_path(tmp_path: Path) -> None:
    first = load_problem_spec(_write_yaml(tmp_path / "first", _v2_data()))
    second = load_problem_spec(_write_yaml(tmp_path / "second", _v2_data()))

    assert first.path != second.path
    assert canonical_problem_spec_json(first) == canonical_problem_spec_json(second)
    assert problem_spec_sha256(first) == problem_spec_sha256(second)
    assert str(first.path) not in canonical_problem_spec_json(first)


def test_canonical_hash_changes_when_problem_semantics_change(tmp_path: Path) -> None:
    baseline = load_problem_spec(_write_yaml(tmp_path, _v2_data(), "baseline.yaml"))
    changed_data = _v2_data()
    changed_data["responses"][0]["direction"] = [0.0, 1.0, 0.0]
    changed = load_problem_spec(_write_yaml(tmp_path, changed_data, "changed.yaml"))

    assert problem_spec_sha256(baseline) != problem_spec_sha256(changed)


def test_explicit_domain_bounds_are_canonical_and_build_the_target_grid(tmp_path: Path) -> None:
    data = _v2_data()
    data["grid"]["domain_bounds_m"] = {
        "lower": [-0.04, -0.02, 0.0],
        "upper": [0.02, 0.02, 0.04],
    }

    spec = load_problem_spec(_write_yaml(tmp_path, data, "domain.yaml"))
    content = problem_spec_to_dict(spec)
    grid = canonical_uniform_cartesian_cell_grid(spec)

    assert spec.grid.domain_bounds_m is not None
    assert spec.grid.domain_bounds_m.lower == pytest.approx((-0.04, -0.02, 0.0))
    assert content["grid"]["domain_bounds_m"] == data["grid"]["domain_bounds_m"]
    assert "domain_bounds_m" not in spec.grid.options
    assert grid.origin == pytest.approx((-0.04, -0.02, 0.0))
    assert grid.spacing == pytest.approx((0.02, 0.02, 0.02))
    assert grid.cell_shape == (3, 2, 2)


@pytest.mark.parametrize(
    "bounds,match",
    [
        ({"lower": [0.0, 0.0, 0.0], "upper": [0.0, 0.02, 0.02]}, "lower < upper"),
        ({"lower": [0.0, 0.0, 0.0], "upper": [0.03, 0.02, 0.02]}, "integer multiple"),
        ({"lower": [0.0, 0.0, 0.0], "upper": [float("inf"), 0.02, 0.02]}, "finite"),
        (
            {"lower": [0.0, 0.0, 0.0], "upper": [0.02, 0.02, 0.02], "extra": 1},
            "unknown keys",
        ),
    ],
)
def test_explicit_domain_bounds_are_strictly_validated(
    tmp_path: Path, bounds: dict, match: str
) -> None:
    data = _v2_data()
    data["grid"]["domain_bounds_m"] = bounds

    with pytest.raises(ValueError, match=match):
        load_problem_spec(_write_yaml(tmp_path, data, "invalid_domain.yaml"))


def test_explicit_domain_bounds_change_hash_but_omission_remains_compatible(tmp_path: Path) -> None:
    baseline = load_problem_spec(_write_yaml(tmp_path, _v2_data(), "baseline.yaml"))
    changed_data = _v2_data()
    changed_data["grid"]["domain_bounds_m"] = {
        "lower": [0.0, 0.0, 0.0],
        "upper": [0.04, 0.04, 0.04],
    }
    changed = load_problem_spec(_write_yaml(tmp_path, changed_data, "domain.yaml"))

    assert baseline.grid.domain_bounds_m is None
    assert "domain_bounds_m" not in problem_spec_to_dict(baseline)["grid"]
    assert problem_spec_sha256(baseline) != problem_spec_sha256(changed)
    with pytest.raises(ValueError, match="domain_bounds_m"):
        canonical_uniform_cartesian_cell_grid(baseline)


def test_g2_domain_bounds_match_the_openfoam_block_mesh_extent() -> None:
    spec = load_problem_spec(Path("examples/g2_openfoam_compile/project.yaml"))
    grid = canonical_uniform_cartesian_cell_grid(spec)

    assert spec.grid.domain_bounds_m is not None
    assert spec.grid.domain_bounds_m.lower == pytest.approx((-1.0, -0.8, -0.6))
    assert spec.grid.domain_bounds_m.upper == pytest.approx((2.0, 0.8, 0.6))
    assert grid.cell_shape == (150, 80, 60)


def test_canonical_hash_changes_with_typed_topology_semantics(tmp_path: Path) -> None:
    baseline = load_problem_spec(_write_yaml(tmp_path, _v2_data(), "topology_baseline.yaml"))
    changed_data = _v2_data()
    changed_data["topology_policy"]["minimum_gap_m"] = 0.009
    changed = load_problem_spec(_write_yaml(tmp_path, changed_data, "topology_changed.yaml"))

    assert problem_spec_sha256(baseline) != problem_spec_sha256(changed)
    assert json.loads(canonical_problem_spec_json(baseline))["topology_policy"] == problem_spec_to_dict(
        baseline
    )["topology_policy"]


@pytest.mark.parametrize("semantic", ["motion", "plugin"])
def test_canonical_hash_changes_with_motion_and_response_options(
    tmp_path: Path, semantic: str
) -> None:
    baseline = load_problem_spec(_write_yaml(tmp_path, _v2_data(), f"{semantic}_baseline.yaml"))
    changed_data = _v2_data()
    if semantic == "motion":
        changed_data["flow_cases"][0]["motion_profiles"]["moving_ground"]["velocity_mps"][0] = 31.0
    else:
        changed_data["responses"][4]["options"]["parameters"]["radius_m"] = 0.2
    changed = load_problem_spec(_write_yaml(tmp_path, changed_data, f"{semantic}_changed.yaml"))

    assert problem_spec_sha256(baseline) != problem_spec_sha256(changed)


def test_snapshot_readback_contains_matching_hash(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_yaml(tmp_path, _v2_data()))
    snapshot_path = write_problem_spec_snapshot(spec, tmp_path / "snapshots" / "problem_spec.json")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert snapshot["kind"] == "cfd_optimization_problem_spec"
    assert snapshot["schema_version"] == 2
    assert snapshot["problem"] == problem_spec_to_dict(spec)
    assert snapshot["problem_spec_sha256"] == problem_spec_sha256(spec)
    canonical_readback = json.dumps(snapshot["problem"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canonical_readback.encode("utf-8")).hexdigest() == snapshot["problem_spec_sha256"]


def test_legacy_snapshot_records_not_execution_ready(tmp_path: Path) -> None:
    legacy = {
        "objective": {
            "type": "maximize_downforce_with_efficiency_constraint",
            "efficiency_min": 3.0,
        },
        "operating_point": {"velocity_mps": 11.0, "density": 1.229, "viscosity": 1.73e-5},
    }
    spec = load_problem_spec(_write_yaml(tmp_path, legacy, "legacy_snapshot_source.yaml"))
    snapshot_path = write_problem_spec_snapshot(spec, tmp_path / "legacy_snapshot.json")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert snapshot["migration"]["migrated"] is True
    assert snapshot["migration"]["execution_ready"] is False
    assert snapshot["problem_spec_sha256"] == problem_spec_sha256(spec)


def test_immutable_nested_mappings_are_json_serializable(tmp_path: Path) -> None:
    data = _v2_data()
    data["grid"]["solver_options"] = {"levels": [1, 2, 3]}
    data["flow_cases"][0]["turbulence"]["coefficients"] = {"beta": 0.075}
    spec = load_problem_spec(_write_yaml(tmp_path, data))

    content = problem_spec_to_dict(spec)
    serialized = canonical_problem_spec_json(spec)

    assert json.loads(serialized) == content
    assert content["grid"]["solver_options"]["levels"] == [1, 2, 3]
    assert content["topology_policy"]["solid_connectivity"]["mode"] == "required_root_groups"
    assert content["topology_policy"]["root_groups"][0]["region_ids"] == ["mount"]
