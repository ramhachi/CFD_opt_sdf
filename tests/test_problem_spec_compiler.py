"""Tests for the ProblemSpec-to-algebra compiler (DF1)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import yaml

from cfd_sdf.design_transform import ConeFilter, DesignTransform, RampInterpolation, TanhProjection
from cfd_sdf.problem_spec import load_problem_spec
from cfd_sdf.problem_spec_compiler import (
    ProblemCompileError,
    VolumeBudget,
    compile_problem,
)


def _spec_data() -> dict:
    return {
        "schema_version": 2,
        "problem_id": "compiler_fixture",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        },
        "grid": {"kind": "uniform_cartesian", "voxel_size_m": 0.05, "padding_m": 0.0},
        "reference_values": {"area_m2": 1.2, "length_m": 0.8, "moment_center_m": [0.25, 0.0, 0.0]},
        "geometry_regions": [
            {"id": "design_box", "role": "design_domain", "file": "geometry/design_box.stl"}
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
                "boundary_conditions": {"inlet": "freestream", "outlet": "pressure_outlet"},
                "motion_profiles": {},
            }
        ],
        "responses": [
            {"id": "drag", "kind": "force", "flow_case_id": "straight", "direction": [1.0, 0.0, 0.0]},
            {"id": "downforce", "kind": "force", "flow_case_id": "straight", "direction": [0.0, 0.0, -1.0]},
        ],
        "objectives": [
            {
                "id": "max_downforce",
                "sense": "maximize",
                "terms": [{"coefficient": 1.0, "flow_case_id": "straight", "response_id": "downforce"}],
            }
        ],
        "constraints": [
            {
                "id": "efficiency",
                "relation": ">=",
                "limit": 0.0,
                "terms": [
                    {"coefficient": 2.0, "flow_case_id": "straight", "response_id": "drag"},
                    {"coefficient": -1.0, "flow_case_id": "straight", "response_id": "downforce"},
                ],
            }
        ],
        "topology_policy": {
            "minimum_solid_width_m": 0.15,
            "minimum_void_width_m": None,
            "minimum_gap_m": None,
            "erosion_radius_m": None,
            "root_groups": [],
            "solid_connectivity": {
                "mode": "single_component",
                "required_root_group_ids": [],
                "max_components": 1,
                "evaluate_eroded": False,
            },
            "void_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
                "evaluate_eroded": False,
            },
        },
    }


def _spec(tmp_path: Path, data: dict | None = None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "problem.yaml"
    path.write_text(yaml.safe_dump(data or _spec_data(), sort_keys=False), encoding="utf-8")
    return load_problem_spec(path)


def test_compile_standardizes_sense_and_composes_primitives(tmp_path: Path):
    compiled = compile_problem(_spec(tmp_path))
    assert compiled.objectives[0].sense == "maximize"
    assert compiled.objectives[0].sign == -1.0
    assert compiled.required_primitives() == {("straight", "drag"), ("straight", "downforce")}

    values = {("straight", "drag"): 1.5, ("straight", "downforce"): 0.8}
    assert compiled.objective_value(values) == pytest.approx(-0.8)

    gradients = {
        ("straight", "drag"): np.full(3, 0.5),
        ("straight", "downforce"): np.full(3, 2.0),
    }
    assert np.allclose(compiled.objective_gradient(gradients), np.full(3, -2.0))

    constraints = compiled.constraint_values(values)
    assert constraints["efficiency"] == pytest.approx(-(2.0 * 1.5 - 0.8))
    constraint_gradients = compiled.constraint_gradients(gradients)
    assert np.allclose(constraint_gradients["efficiency"], -(2.0 * 0.5 - 2.0))


def test_compile_records_topology_geometry_requirements(tmp_path: Path):
    compiled = compile_problem(_spec(tmp_path))
    requirements = {item.requirement_id: item for item in compiled.geometry_requirements}
    assert requirements["minimum_solid_width_m"].kind == "minimum_length_scale"
    assert requirements["minimum_solid_width_m"].declared["value_m"] == pytest.approx(0.15)
    assert requirements["solid_connectivity_connectivity"].kind == "connectivity"
    assert requirements["solid_connectivity_connectivity"].declared["mode"] == "single_component"
    assert "void_connectivity_connectivity" not in requirements


def test_missing_primitive_is_fail_closed(tmp_path: Path):
    compiled = compile_problem(_spec(tmp_path))
    with pytest.raises(ProblemCompileError, match="not provided"):
        compiled.enforce_primitives({("straight", "drag")})
    with pytest.raises(KeyError):
        compiled.objective_value({("straight", "drag"): 1.0})


def test_unsupported_response_kind_and_relation_are_rejected(tmp_path: Path):
    data = _spec_data()
    data["responses"].append(
        {"id": "pitch_moment", "kind": "moment", "flow_case_id": "straight", "direction": [0.0, 1.0, 0.0]}
    )
    data["objectives"][0]["terms"] = [
        {"coefficient": 1.0, "flow_case_id": "straight", "response_id": "pitch_moment"}
    ]
    with pytest.raises(ProblemCompileError, match="moment"):
        compile_problem(_spec(tmp_path, data))

    equality = _spec_data()
    equality["constraints"][0]["relation"] = "=="
    with pytest.raises(ProblemCompileError, match="equality"):
        compile_problem(_spec(tmp_path / "eq", equality))

    undeclared = _spec_data()
    undeclared["objectives"][0]["terms"][0]["response_id"] = "lift"
    with pytest.raises(ValueError):
        _spec(tmp_path / "undeclared", undeclared)


def test_flow_case_mismatch_is_rejected(tmp_path: Path):
    data = deepcopy(_spec_data())
    data["flow_cases"].append(deepcopy(data["flow_cases"][0]))
    data["flow_cases"][1]["id"] = "yawed"
    data["responses"].append(
        {"id": "downforce_yawed", "kind": "force", "flow_case_id": "yawed", "direction": [0.0, 0.0, -1.0]}
    )
    data["objectives"][0]["terms"] = [
        {"coefficient": 1.0, "flow_case_id": "straight", "response_id": "downforce_yawed"}
    ]
    # the loader already binds a response to its declared flow case; the
    # compiler keeps its own check as defence in depth
    with pytest.raises(ValueError, match="binds response"):
        _spec(tmp_path, data)


def test_multipoint_terms_aggregate_both_primitives(tmp_path: Path):
    data = _spec_data()
    data["flow_cases"].append(deepcopy(data["flow_cases"][0]))
    data["flow_cases"][1]["id"] = "yawed"
    data["responses"].append(
        {"id": "downforce_yawed", "kind": "force", "flow_case_id": "yawed", "direction": [0.0, 0.0, -1.0]}
    )
    data["objectives"] = [
        {
            "id": "weighted_downforce",
            "sense": "maximize",
            "terms": [
                {"coefficient": 0.7, "flow_case_id": "straight", "response_id": "downforce"},
                {"coefficient": 0.3, "flow_case_id": "yawed", "response_id": "downforce_yawed"},
            ],
        }
    ]
    data["constraints"] = []
    compiled = compile_problem(_spec(tmp_path, data))
    values = {
        ("straight", "downforce"): 1.0,
        ("yawed", "downforce_yawed"): 2.0,
    }
    assert compiled.objective_value(values) == pytest.approx(-(0.7 * 1.0 + 0.3 * 2.0))
    gradients = {
        ("straight", "downforce"): np.array([1.0, 0.0]),
        ("yawed", "downforce_yawed"): np.array([0.0, 1.0]),
    }
    assert np.allclose(compiled.objective_gradient(gradients), np.array([-0.7, -0.3]))


def test_volume_gradient_matches_fd_in_projection_space_with_ramp(tmp_path: Path):
    shape = (4, 3, 2)
    active = np.ones(int(np.prod(shape)), dtype=bool)
    transform = DesignTransform(
        shape=shape,
        spacing_m=1.0,
        active_mask=active,
        filter=ConeFilter(shape=shape, spacing_m=1.0, active_mask=active, radius_m=1.0),
        projection=TanhProjection(8.0, 0.5),
        ramp=RampInterpolation(30.0),
    )
    rng = np.random.default_rng(7)
    rho = np.clip(rng.uniform(0.2, 0.8, size=active.size), 0.0, 1.0)
    direction = rng.normal(size=active.size)
    from cfd_sdf.problem_spec_compiler import VolumeOccupationConstraint

    constraint = VolumeOccupationConstraint("volume_fraction_max", limit=0.2)
    step = 1e-6
    fd = (
        constraint.value(transform, rho + step * direction)
        - constraint.value(transform, rho - step * direction)
    ) / (2 * step)
    gradient = constraint.gradient(transform, rho)
    assert float(np.dot(gradient, direction)) == pytest.approx(fd, rel=1e-4, abs=1e-9)

    # mutation test: the RAMP-space pullback is a different function at q > 0
    state = transform.forward(rho)
    g_projected = np.zeros_like(state.rho_projected)
    g_projected[active] = 1.0 / active.size
    ramp_space = transform.pullback_from_beta(rho, g_projected)
    assert float(np.dot(ramp_space, direction)) != pytest.approx(fd, rel=1e-2)


def test_compile_problem_attaches_explicit_volume_budget(tmp_path: Path):
    spec = _spec(tmp_path)
    without = compile_problem(spec)
    assert without.volume_constraint is None
    assert without.solved_set()["volume"] is None

    with_budget = compile_problem(
        spec, volume_budget=VolumeBudget("volume_fraction_max", 0.5)
    )
    assert with_budget.volume_constraint is not None
    solved = with_budget.solved_set()
    assert solved["volume"]["limit"] == pytest.approx(0.5)
    assert solved["volume"]["field"] == "rho_projected"
    assert solved["volume"]["source"] == "compile_time_declaration"
    assert with_budget.compiled_problem_hash() != without.compiled_problem_hash()

    with pytest.raises(ProblemCompileError, match="limit"):
        VolumeBudget("volume_fraction_max", 1.5)
    with pytest.raises(ProblemCompileError, match="constraint_id"):
        VolumeBudget("", 0.5)


def test_volume_constraint_uses_projected_field(tmp_path: Path):
    shape = (4, 3, 2)
    active = np.ones(int(np.prod(shape)), dtype=bool)
    transform = DesignTransform(
        shape=shape,
        spacing_m=1.0,
        active_mask=active,
        filter=ConeFilter(shape=shape, spacing_m=1.0, active_mask=active, radius_m=1.0),
        projection=TanhProjection(8.0, 0.5),
        ramp=RampInterpolation(0.0),
    )
    rho = np.full(active.size, 0.25)
    compiled = compile_problem(_spec(tmp_path))
    from cfd_sdf.problem_spec_compiler import VolumeOccupationConstraint

    constraint = VolumeOccupationConstraint("volume_fraction_max", limit=0.2)
    projected = transform.forward(rho).rho_projected
    assert constraint.value(transform, rho) == pytest.approx(float(np.mean(projected)) - 0.2)
    gradient = constraint.gradient(transform, rho)
    direction = np.zeros(active.size)
    direction[0] = 1.0
    step = 1e-6
    fd = (
        constraint.value(transform, rho + step * direction)
        - constraint.value(transform, rho - step * direction)
    ) / (2 * step)
    assert float(np.dot(gradient, direction)) == pytest.approx(fd, rel=1e-4, abs=1e-9)
    assert compiled.volume_constraint is None
