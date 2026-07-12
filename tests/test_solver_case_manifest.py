from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256
from cfd_sdf.solver_case_manifest import (
    build_openfoam_solver_case_manifest,
    write_openfoam_solver_case_manifest,
)


EXAMPLE = Path("examples/generic_problem_v2/project.yaml")
PATCHES = ("inlet", "outlet", "ground")


def _valid_data() -> dict:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for case in data["flow_cases"]:
        case["turbulence"].update(
            turbulence_intensity=0.05,
            turbulence_length_scale_m=0.2,
        )
    data["flow_cases"][0]["motion_profiles"]["moving_ground"]["boundary_ids"] = ["ground"]
    data["flow_cases"][1]["boundary_conditions"]["ground"] = "stationary_wall"
    data["responses"] = [
        {
            "id": "straight_force",
            "kind": "force",
            "flow_case_id": "straight",
            "direction": [1.0, 0.0, 0.0],
        },
        {
            "id": "yaw_force",
            "kind": "force",
            "flow_case_id": "yawed",
            "direction": [0.0, 1.0, 0.0],
        },
    ]
    data["objectives"] = [
        {
            "id": "multipoint_objective",
            "sense": "minimize",
            "terms": [
                {"coefficient": 0.7, "flow_case_id": "straight", "response_id": "straight_force"},
                {"coefficient": 0.3, "flow_case_id": "yawed", "response_id": "yaw_force"},
            ],
        }
    ]
    data["constraints"] = []
    return data


def _load(tmp_path: Path, data: dict, name: str = "problem.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_problem_spec(path)


def _reasons(manifest) -> set[str]:
    return set(manifest.unsupported).union(
        reason for plan in manifest.flow_cases for reason in plan.unsupported
    )


def test_valid_two_flow_force_manifest_is_compile_ready(tmp_path: Path) -> None:
    spec = _load(tmp_path, _valid_data())
    manifest = build_openfoam_solver_case_manifest(spec, available_patch_ids=PATCHES)

    assert manifest.compile_ready is True
    assert manifest.unsupported == ()
    assert manifest.problem_spec_sha256 == problem_spec_sha256(spec)
    assert [plan.case_directory_name for plan in manifest.flow_cases] == [
        "flow_straight",
        "flow_yawed",
    ]
    assert [plan.supported_response_ids for plan in manifest.flow_cases] == [
        ("straight_force",),
        ("yaw_force",),
    ]
    straight = manifest.flow_cases[0]
    assert straight.requested["convergence_criteria"] == {
        "primal_final_residual_max": 1.0e-6,
        "normalized_mass_imbalance_max": 1.0e-4,
        "response_stationarity_window": 20,
        "response_relative_range_max": 1.0e-3,
        "adjoint_final_residual_max": 1.0e-6,
    }
    assert straight.generated["fluid"]["kinematic_viscosity_m2_s"] == pytest.approx(1.8e-5 / 1.225)
    assert straight.generated["speed_mps"] == pytest.approx(30.0)
    expected_k = 1.5 * (30.0 * 0.05) ** 2
    expected_omega = expected_k**0.5 / ((0.09**0.25) * 0.2)
    assert straight.generated["turbulence"]["k_m2_s2"] == pytest.approx(expected_k)
    assert straight.generated["turbulence"]["omega_s_inv"] == pytest.approx(expected_omega)
    assert straight.generated["boundary_conditions"]["ground"]["motion_profile_id"] == "moving_ground"
    assert straight.generated["boundary_conditions"]["ground"]["U"]["value"] == (30.0, 0.0, 0.0)
    force = straight.generated["responses"][0]
    assert force["Aref"] == pytest.approx(1.2)
    assert force["UInf"] == pytest.approx(30.0)


def test_laminar_is_supported_with_null_k_and_omega(tmp_path: Path) -> None:
    data = _valid_data()
    for case in data["flow_cases"]:
        case["turbulence"] = {"model": "laminar"}
    spec = _load(tmp_path, data)

    manifest = build_openfoam_solver_case_manifest(spec, available_patch_ids=PATCHES)

    assert manifest.compile_ready is True
    for plan in manifest.flow_cases:
        assert plan.generated["turbulence"]["k_m2_s2"] is None
        assert plan.generated["turbulence"]["omega_s_inv"] is None


def test_manifest_write_is_deterministic_and_copy_safe(tmp_path: Path) -> None:
    spec = _load(tmp_path, _valid_data())
    manifest = build_openfoam_solver_case_manifest(spec, available_patch_ids=PATCHES)
    first = write_openfoam_solver_case_manifest(manifest, tmp_path / "a" / "manifest.json")
    second = write_openfoam_solver_case_manifest(manifest, tmp_path / "b" / "manifest.json")

    assert first.read_bytes() == second.read_bytes()
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(second.read_bytes()).hexdigest()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload == manifest.to_dict()
    copied = manifest.to_dict()
    copied["flow_cases"][0]["generated"]["speed_mps"] = -1
    assert manifest.flow_cases[0].generated["speed_mps"] == pytest.approx(30.0)
    with pytest.raises(TypeError):
        manifest.flow_cases[0].generated["speed_mps"] = -1


def test_incomplete_problem_and_octree_are_global_unsupported(tmp_path: Path) -> None:
    incomplete = _valid_data()
    incomplete["geometry_regions"] = [
        region for region in incomplete["geometry_regions"] if region["role"] != "design_domain"
    ]
    incomplete_manifest = build_openfoam_solver_case_manifest(
        _load(tmp_path, incomplete, "incomplete.yaml"), available_patch_ids=PATCHES
    )
    assert "problem_spec_not_execution_ready" in incomplete_manifest.unsupported
    assert incomplete_manifest.compile_ready is False

    octree = _valid_data()
    octree["grid"]["kind"] = "octree_amr"
    octree_manifest = build_openfoam_solver_case_manifest(
        _load(tmp_path, octree, "octree.yaml"), available_patch_ids=PATCHES
    )
    assert "unsupported_grid_kind:octree_amr" in octree_manifest.unsupported
    assert octree_manifest.compile_ready is False


def test_unsupported_fluid_model_is_reported(tmp_path: Path) -> None:
    data = _valid_data()
    data["flow_cases"][0]["fluid"]["model"] = "compressible_ideal_gas"
    manifest = build_openfoam_solver_case_manifest(_load(tmp_path, data), available_patch_ids=PATCHES)

    assert "unsupported_fluid_model:compressible_ideal_gas" in _reasons(manifest)
    assert manifest.compile_ready is False


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda data: data["flow_cases"][0].update(turbulence={"model": "spalart_allmaras"}),
            "unsupported_turbulence_model:spalart_allmaras",
        ),
        (
            lambda data: data["flow_cases"][0]["turbulence"].pop("turbulence_intensity"),
            "invalid_turbulence_intensity",
        ),
        (
            lambda data: data["flow_cases"][0]["turbulence"].update(turbulence_length_scale_m=0),
            "invalid_turbulence_length_scale_m",
        ),
    ],
)
def test_turbulence_model_and_options_are_reported_as_unsupported(
    tmp_path: Path, mutation, reason: str
) -> None:
    data = _valid_data()
    mutation(data)
    manifest = build_openfoam_solver_case_manifest(_load(tmp_path, data), available_patch_ids=PATCHES)

    assert reason in _reasons(manifest)
    assert manifest.compile_ready is False


def test_boundary_kind_and_available_patch_coverage_are_reported(tmp_path: Path) -> None:
    data = _valid_data()
    data["flow_cases"][0]["boundary_conditions"]["inlet"] = "velocity_inlet_typo"
    manifest = build_openfoam_solver_case_manifest(
        _load(tmp_path, data), available_patch_ids=(*PATCHES, "upper")
    )

    reasons = _reasons(manifest)
    assert "unsupported_boundary_condition:inlet:velocity_inlet_typo" in reasons
    assert "undeclared_available_patch:upper" in reasons
    assert manifest.compile_ready is False


def test_unknown_declared_patch_is_reported(tmp_path: Path) -> None:
    data = _valid_data()
    data["flow_cases"][0]["boundary_conditions"]["ghost"] = "symmetry"
    manifest = build_openfoam_solver_case_manifest(_load(tmp_path, data), available_patch_ids=PATCHES)

    assert "unknown_boundary_patch:ghost" in _reasons(manifest)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda data: data["flow_cases"][0]["motion_profiles"]["moving_ground"].update(
                kind="rotation"
            ),
            "unsupported_motion_profile_kind:moving_ground:rotation",
        ),
        (
            lambda data: data["flow_cases"][0]["motion_profiles"]["moving_ground"].pop(
                "boundary_ids"
            ),
            "invalid_motion_profile_boundary_ids:moving_ground",
        ),
        (
            lambda data: data["flow_cases"][0]["motion_profiles"]["moving_ground"].update(
                velocity_mps=[1.0, 2.0]
            ),
            "invalid_motion_profile_velocity_mps:moving_ground",
        ),
    ],
)
def test_motion_profile_errors_are_explicit(tmp_path: Path, mutation, reason: str) -> None:
    data = _valid_data()
    mutation(data)
    manifest = build_openfoam_solver_case_manifest(_load(tmp_path, data), available_patch_ids=PATCHES)

    reasons = _reasons(manifest)
    assert reason in reasons
    assert "moving_wall_requires_exactly_one_motion_profile:ground" in reasons
    assert manifest.compile_ready is False


def test_non_force_response_is_not_silently_dropped(tmp_path: Path) -> None:
    data = _valid_data()
    data["responses"][1].update(kind="moment")
    manifest = build_openfoam_solver_case_manifest(_load(tmp_path, data), available_patch_ids=PATCHES)

    yawed = manifest.flow_cases[1]
    assert "unsupported_response_kind:yaw_force:moment" in yawed.unsupported
    assert yawed.supported_response_ids == ()
    assert manifest.compile_ready is False


def test_flow_case_without_response_is_unsupported(tmp_path: Path) -> None:
    data = _valid_data()
    data["responses"] = [data["responses"][0]]
    data["objectives"][0]["terms"] = [data["objectives"][0]["terms"][0]]
    spec = _load(tmp_path, data)
    manifest = build_openfoam_solver_case_manifest(spec, available_patch_ids=PATCHES)

    assert "no_responses_for_flow_case" in manifest.flow_cases[1].unsupported
    assert manifest.compile_ready is False


def test_duplicate_available_patch_ids_are_global_unsupported(tmp_path: Path) -> None:
    spec = _load(tmp_path, _valid_data())
    manifest = build_openfoam_solver_case_manifest(
        spec, available_patch_ids=("inlet", "outlet", "ground", "ground")
    )

    assert "duplicate_available_patch_id" in manifest.unsupported
    assert manifest.compile_ready is False


def test_unsafe_patch_ids_are_reported_before_rendering(tmp_path: Path) -> None:
    data = _valid_data()
    data["flow_cases"][0]["boundary_conditions"]["bad/patch"] = "symmetry"
    spec = _load(tmp_path, data)
    manifest = build_openfoam_solver_case_manifest(
        spec, available_patch_ids=(*PATCHES, "bad/patch", "bad available")
    )

    assert "unsafe_available_patch_id:bad available" in manifest.unsupported
    assert "unsafe_boundary_patch_id:bad/patch" in manifest.flow_cases[0].unsupported
    assert manifest.compile_ready is False
