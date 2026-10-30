from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import trimesh
import yaml

from cfd_sdf.openfoam import generate_openfoam_case, problem_spec_to_project_config
from cfd_sdf.problem_spec import load_problem_spec, problem_spec_sha256
from cfd_sdf.sdf import build_fields


def _box(path: Path, center: tuple[float, float, float], extents: tuple[float, float, float]) -> None:
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)


def _spec_dict(*, extra_flow_case: bool = False, extra_flow_case_velocity: tuple = (25.0, 0.0, 0.0)) -> dict:
    flow_cases = [
        {
            "id": "straight",
            "freestream_velocity_mps": [30.0, 0.0, 0.0],
            "fluid": {
                "model": "incompressible_newtonian",
                "density_kg_m3": 1.225,
                "dynamic_viscosity_pa_s": 1.8e-05,
            },
            "turbulence": {"model": "k_omega_sst"},
            "boundary_conditions": {"inlet": "freestream", "outlet": "pressure_outlet"},
            "motion_profiles": {},
        }
    ]
    if extra_flow_case:
        flow_cases.append(
            {
                "id": "second",
                "freestream_velocity_mps": list(extra_flow_case_velocity),
                "fluid": {
                    "model": "incompressible_newtonian",
                    "density_kg_m3": 1.225,
                    "dynamic_viscosity_pa_s": 1.8e-05,
                },
                "turbulence": {"model": "k_omega_sst"},
                "boundary_conditions": {"inlet": "freestream", "outlet": "pressure_outlet"},
                "motion_profiles": {},
            }
        )
    return {
        "schema_version": 2,
        "problem_id": "adapter_fixture",
        "units": {"length": "m", "time": "s", "mass": "kg"},
        "coordinate_frame": {
            "id": "global_frame",
            "origin_m": [0.0, 0.0, 0.0],
            "basis": {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        },
        "grid": {
            "kind": "uniform_cartesian",
            "voxel_size_m": 0.1,
            "padding_m": 0.0,
            "domain_bounds_m": {"lower": [-1.0, -0.8, -0.6], "upper": [2.0, 0.8, 0.6]},
        },
        "reference_values": {"area_m2": 1.2, "length_m": 0.8, "moment_center_m": [0.25, 0.0, 0.0]},
        "geometry_regions": [
            {"id": "chassis", "role": "fixed_solid", "file": "geometry/chassis.stl"},
            {"id": "wing_initial", "role": "initial_design", "file": "geometry/wing_initial.stl"},
            {"id": "design_domain", "role": "design_domain", "file": "geometry/design_domain.stl"},
            {"id": "keepout", "role": "forbidden_region", "file": "geometry/keepout.stl"},
            {"id": "mount", "role": "root", "file": "geometry/mount.stl"},
        ],
        "flow_cases": flow_cases,
        "responses": [
            {"id": "drag", "kind": "force", "flow_case_id": "straight", "direction": [1.0, 0.0, 0.0]},
            {"id": "downforce", "kind": "force", "flow_case_id": "straight", "direction": [0.0, 0.0, -1.0]},
        ],
        "objectives": [
            {
                "id": "minimize_drag",
                "sense": "minimize",
                "terms": [{"coefficient": 1.0, "flow_case_id": "straight", "response_id": "drag"}],
            }
        ],
        "constraints": [],
        "topology_policy": {
            "root_groups": [],
            "solid_connectivity": {
                "mode": "disabled",
                "required_root_group_ids": [],
                "max_components": None,
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


def _write_spec(tmp_path: Path, **kwargs) -> Path:
    _box(tmp_path / "geometry" / "chassis.stl", (-0.5, 0.0, 0.0), (0.4, 0.3, 0.2))
    _box(tmp_path / "geometry" / "wing_initial.stl", (0.25, 0.0, -0.2), (0.5, 0.6, 0.05))
    _box(tmp_path / "geometry" / "design_domain.stl", (0.25, 0.0, -0.2), (0.7, 0.7, 0.15))
    _box(tmp_path / "geometry" / "keepout.stl", (1.0, 0.0, 0.0), (0.2, 0.2, 0.2))
    _box(tmp_path / "geometry" / "mount.stl", (0.25, 0.0, -0.4), (0.1, 0.1, 0.1))
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(_spec_dict(**kwargs), sort_keys=False), encoding="utf-8")
    return project_yaml


def _write_custom_spec(tmp_path: Path, data: dict) -> Path:
    _box(tmp_path / "geometry" / "chassis.stl", (-0.5, 0.0, 0.0), (0.4, 0.3, 0.2))
    _box(tmp_path / "geometry" / "wing_initial.stl", (0.25, 0.0, -0.2), (0.5, 0.6, 0.05))
    _box(tmp_path / "geometry" / "design_domain.stl", (0.25, 0.0, -0.2), (0.7, 0.7, 0.15))
    _box(tmp_path / "geometry" / "keepout.stl", (1.0, 0.0, 0.0), (0.2, 0.2, 0.2))
    _box(tmp_path / "geometry" / "mount.stl", (0.25, 0.0, -0.4), (0.1, 0.1, 0.1))
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return project_yaml


def test_adapter_maps_geometry_roles_and_operating_point(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    config = problem_spec_to_project_config(spec)

    assert [ref.id for ref in config.fixed_solids] == ["chassis"]
    assert [ref.id for ref in config.design_geometry] == ["wing_initial"]
    assert [ref.id for ref in config.design_domains] == ["design_domain"]
    assert [ref.id for ref in config.forbidden_regions] == ["keepout"]
    assert [root.id for root in config.roots] == ["mount"]
    assert config.roots[0].type == "stl"
    assert config.flow_case_id == "straight"
    assert config.operating_point.velocity_mps == pytest.approx(30.0)
    assert config.operating_point.density == pytest.approx(1.225)
    assert config.operating_point.viscosity == pytest.approx(1.8e-05)
    assert config.problem_spec is spec


def test_stage_v_legacy_boundary_defaults_are_preserved(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    config = problem_spec_to_project_config(spec)
    bundle = build_fields(config)
    case_dir = tmp_path / "case"
    generate_openfoam_case(config, bundle, case_dir)

    mesh = (case_dir / "system" / "blockMeshDict").read_text(encoding="utf-8")
    velocity = (case_dir / "0" / "U").read_text(encoding="utf-8")
    pressure = (case_dir / "0" / "p").read_text(encoding="utf-8")
    assert "sideMin { type symmetryPlane;" in mesh
    assert "bottom { type wall;" in mesh
    assert "sideMin { type symmetryPlane;" in velocity
    assert "bottom { type noSlip;" in velocity
    assert "outlet { type fixedValue; value uniform 0;" in pressure
    metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
    assert metadata["boundary_contract"]["ground_model"] == "stationary_ground"
    assert len(metadata["physical_profile"]["sha256"]) == 64


def test_stage_v_moving_ground_uses_translation_profile_and_aliases(tmp_path: Path) -> None:
    data = _spec_dict()
    data["flow_cases"][0]["boundary_conditions"] = {
        "inlet": "freestream",
        "outlet": "pressure_outlet",
        "ground": "moving_wall",
    }
    data["flow_cases"][0]["motion_profiles"] = {
        "moving_ground": {
            "kind": "translation",
            "boundary_ids": ["ground"],
            "velocity_mps": [30.0, 0.0, 0.0],
        }
    }
    spec = load_problem_spec(_write_custom_spec(tmp_path, data))
    config = problem_spec_to_project_config(spec)
    assert config.boundary_conditions["bottom"] == "moving_wall"
    assert config.motion_profiles["moving_ground"]["boundary_ids"] == ("bottom",)

    bundle = build_fields(config)
    case_dir = tmp_path / "case"
    generate_openfoam_case(config, bundle, case_dir)
    velocity = (case_dir / "0" / "U").read_text(encoding="utf-8")
    assert "bottom { type translatingWallVelocity; U (30 0 0); value uniform (30 0 0);" in velocity
    metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
    assert metadata["boundary_contract"]["patches"]["bottom"] == "moving_wall"
    assert metadata["boundary_contract"]["ground_model"] == "moving_ground"
    assert metadata["boundary_contract"]["motion_profiles"]["moving_ground"]["boundary_ids"] == ["bottom"]
    assert metadata["physical_profile"]["ground_model"] == "moving_ground"
    assert metadata["physical_profile"]["boundary_implementation"]["moving_wall"] == "translatingWallVelocity"
    assert metadata["physical_profile"]["outer_boundary_semantics"]["freestream_velocity_mps"] == [30.0, 0.0, 0.0]
    assert metadata["physical_profile"]["outer_boundary_semantics"]["freestream_pressure_pa"] == 0.0
    assert metadata["physical_profile"]["turbulence_model"] == "kOmegaSST"


def test_stage_v_far_field_profile_matches_mesh_and_fields(tmp_path: Path) -> None:
    data = _spec_dict()
    data["flow_cases"][0]["boundary_conditions"] = {
        "inlet": "far_field",
        "outlet": "far_field",
        "spanMin": "far_field",
        "spanMax": "far_field",
        "upper": "far_field",
        "ground": "stationary_wall",
    }
    spec = load_problem_spec(_write_custom_spec(tmp_path, data))
    config = problem_spec_to_project_config(spec)
    bundle = build_fields(config)
    case_dir = tmp_path / "case"
    generate_openfoam_case(config, bundle, case_dir)

    mesh = (case_dir / "system" / "blockMeshDict").read_text(encoding="utf-8")
    velocity = (case_dir / "0" / "U").read_text(encoding="utf-8")
    pressure = (case_dir / "0" / "p").read_text(encoding="utf-8")
    for patch in ("inlet", "outlet", "sideMin", "sideMax", "top"):
        assert f"{patch} {{ type patch;" in mesh
        assert f"{patch} {{ type freestreamVelocity;" in velocity
        assert f"{patch} {{ type freestreamPressure;" in pressure
    assert "bottom { type wall;" in mesh
    assert "bottom { type noSlip;" in velocity


def test_physical_profile_hash_includes_operating_point_and_turbulence(tmp_path: Path) -> None:
    data = _spec_dict()
    data["flow_cases"][0]["boundary_conditions"] = {
        "inlet": "far_field",
        "outlet": "far_field",
        "ground": "moving_wall",
    }
    data["flow_cases"][0]["motion_profiles"] = {
        "moving_ground": {
            "kind": "translation",
            "boundary_ids": ["ground"],
            "velocity_mps": [30.0, 0.0, 0.0],
        }
    }
    first = _write_custom_spec(tmp_path / "first", data)
    second_data = deepcopy(data)
    second_data["flow_cases"][0]["freestream_velocity_mps"] = [31.0, 0.0, 0.0]
    second = _write_custom_spec(tmp_path / "second", second_data)

    metadata = []
    for index, path in enumerate((first, second)):
        spec = load_problem_spec(path)
        config = problem_spec_to_project_config(spec)
        bundle = build_fields(config)
        case_dir = tmp_path / f"case_{index}"
        generate_openfoam_case(config, bundle, case_dir)
        metadata.append(json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8")))

    first_profile = metadata[0]["physical_profile"]
    second_profile = metadata[1]["physical_profile"]
    assert first_profile["outer_boundary_semantics"]["freestream_velocity_mps"] == [30.0, 0.0, 0.0]
    assert second_profile["outer_boundary_semantics"]["freestream_velocity_mps"] == [31.0, 0.0, 0.0]
    assert first_profile["sha256"] != second_profile["sha256"]


@pytest.mark.parametrize(
    ("boundaries", "match"),
    [
        ({"unknown": "symmetry"}, "Unsupported Stage V boundary patch"),
        ({"ground": "unsupported"}, "Unsupported Stage V boundary kind"),
        ({"ground": "stationary_wall", "bottom": "moving_wall"}, "Duplicate Stage V boundary alias"),
    ],
)
def test_stage_v_boundary_profile_fails_closed(tmp_path: Path, boundaries: dict, match: str) -> None:
    data = _spec_dict()
    data["flow_cases"][0]["boundary_conditions"] = boundaries
    spec = load_problem_spec(_write_custom_spec(tmp_path, data))
    with pytest.raises(ValueError, match=match):
        problem_spec_to_project_config(spec)


def test_candidate_stl_overrides_initial_design(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    candidate = tmp_path / "candidate.stl"
    _box(candidate, (0.25, 0.0, -0.2), (0.3, 0.3, 0.05))

    config = problem_spec_to_project_config(spec, candidate_stl=candidate)

    assert [ref.id for ref in config.design_geometry] == ["candidate"]
    assert config.design_geometry[0].file == candidate.resolve()


def test_missing_design_geometry_is_refused(tmp_path: Path) -> None:
    data = _spec_dict()
    data["geometry_regions"] = [
        region for region in data["geometry_regions"] if region["role"] != "initial_design"
    ]
    _box(tmp_path / "geometry" / "chassis.stl", (-0.5, 0.0, 0.0), (0.4, 0.3, 0.2))
    _box(tmp_path / "geometry" / "design_domain.stl", (0.25, 0.0, -0.2), (0.7, 0.7, 0.15))
    _box(tmp_path / "geometry" / "keepout.stl", (1.0, 0.0, 0.0), (0.2, 0.2, 0.2))
    _box(tmp_path / "geometry" / "mount.stl", (0.25, 0.0, -0.4), (0.1, 0.1, 0.1))
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    spec = load_problem_spec(project_yaml)

    with pytest.raises(ValueError, match="no initial_design geometry"):
        problem_spec_to_project_config(spec)


def test_ambiguous_flow_case_is_refused_unless_selected_explicitly(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path, extra_flow_case=True))

    with pytest.raises(ValueError, match="more than one flow_cases"):
        problem_spec_to_project_config(spec)

    config = problem_spec_to_project_config(spec, flow_case_id="second")
    assert config.flow_case_id == "second"
    assert config.operating_point.velocity_mps == pytest.approx(25.0)

    with pytest.raises(ValueError, match="no flow_cases..\\.id"):
        problem_spec_to_project_config(spec, flow_case_id="nope")


def test_freestream_velocity_must_align_with_global_x(tmp_path: Path) -> None:
    spec = load_problem_spec(
        _write_spec(tmp_path, extra_flow_case=True, extra_flow_case_velocity=(30.0, 5.0, 0.0))
    )

    with pytest.raises(ValueError, match="global \\+x axis"):
        problem_spec_to_project_config(spec, flow_case_id="second")


def test_unsupported_turbulence_model_is_refused(tmp_path: Path) -> None:
    data = _spec_dict()
    data["flow_cases"][0]["turbulence"]["model"] = "spalart_allmaras"
    _box(tmp_path / "geometry" / "chassis.stl", (-0.5, 0.0, 0.0), (0.4, 0.3, 0.2))
    _box(tmp_path / "geometry" / "wing_initial.stl", (0.25, 0.0, -0.2), (0.5, 0.6, 0.05))
    _box(tmp_path / "geometry" / "design_domain.stl", (0.25, 0.0, -0.2), (0.7, 0.7, 0.15))
    _box(tmp_path / "geometry" / "keepout.stl", (1.0, 0.0, 0.0), (0.2, 0.2, 0.2))
    _box(tmp_path / "geometry" / "mount.stl", (0.25, 0.0, -0.4), (0.1, 0.1, 0.1))
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    spec = load_problem_spec(project_yaml)

    with pytest.raises(ValueError, match="kOmegaSST"):
        problem_spec_to_project_config(spec)


def test_laminar_turbulence_model_generates_case_without_turbulence_fields(tmp_path: Path) -> None:
    data = _spec_dict()
    data["flow_cases"][0]["turbulence"]["model"] = "laminar"
    _box(tmp_path / "geometry" / "chassis.stl", (-0.5, 0.0, 0.0), (0.4, 0.3, 0.2))
    _box(tmp_path / "geometry" / "wing_initial.stl", (0.25, 0.0, -0.2), (0.5, 0.6, 0.05))
    _box(tmp_path / "geometry" / "design_domain.stl", (0.25, 0.0, -0.2), (0.7, 0.7, 0.15))
    _box(tmp_path / "geometry" / "keepout.stl", (1.0, 0.0, 0.0), (0.2, 0.2, 0.2))
    _box(tmp_path / "geometry" / "mount.stl", (0.25, 0.0, -0.4), (0.1, 0.1, 0.1))
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    spec = load_problem_spec(project_yaml)

    config = problem_spec_to_project_config(spec)
    assert config.turbulence_model == "laminar"

    bundle = build_fields(config)
    case_dir = tmp_path / "case"
    generate_openfoam_case(config, bundle, case_dir)

    turbulence_properties = (case_dir / "constant" / "turbulenceProperties").read_text(encoding="utf-8")
    assert "simulationType laminar;" in turbulence_properties
    assert "RASModel" not in turbulence_properties

    for name in ("k", "omega", "nut"):
        assert not (case_dir / "0" / name).exists()
    assert (case_dir / "0" / "U").exists()
    assert (case_dir / "0" / "p").exists()

    fv_schemes = (case_dir / "system" / "fvSchemes").read_text(encoding="utf-8")
    assert "div(phi,k)" not in fv_schemes
    fv_solution = (case_dir / "system" / "fvSolution").read_text(encoding="utf-8")
    assert "k 0.7" not in fv_solution

    metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
    assert metadata["operating_point"]["turbulence_model"] == "laminar"


def test_fv_solution_uses_convergence_verified_relaxation_and_iteration_cap(tmp_path: Path) -> None:
    """Regression test for the V3 grid-convergence stall.

    The old p=0.3/U=0.7 relaxation left the finest qualification grid (V3, ~1.3M cells, 8.7k
    concave cells near the body) only marginally stable: restarting the stalled V3 run
    (work/stage_sv_qualified_laminar/candidate_a_seed_reshape/V3) with those factors unchanged
    reproduced a flat p residual (~1.9e-4 against the 1e-5 gate, neither decaying nor growing).
    Reducing damping further (dropping the p relaxation, or raising U to 0.9) made it worse: p
    decayed briefly then grew without bound. Only increasing damping (p 0.2, U 0.5) produced
    strictly monotonic, unbounded decay when tested the same way (see
    work/stage_v_grid_convergence_fix/relax_probe_more_damping/log.simpleFoam) -- so the fix is
    more conservative relaxation, plus more iteration headroom (500 -> 1500) since heavier
    damping converges in more iterations, not fewer.
    """
    data = _spec_dict()
    _box(tmp_path / "geometry" / "chassis.stl", (-0.5, 0.0, 0.0), (0.4, 0.3, 0.2))
    _box(tmp_path / "geometry" / "wing_initial.stl", (0.25, 0.0, -0.2), (0.5, 0.6, 0.05))
    _box(tmp_path / "geometry" / "design_domain.stl", (0.25, 0.0, -0.2), (0.7, 0.7, 0.15))
    _box(tmp_path / "geometry" / "keepout.stl", (1.0, 0.0, 0.0), (0.2, 0.2, 0.2))
    _box(tmp_path / "geometry" / "mount.stl", (0.25, 0.0, -0.4), (0.1, 0.1, 0.1))
    project_yaml = tmp_path / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    spec = load_problem_spec(project_yaml)
    config = problem_spec_to_project_config(spec)

    bundle = build_fields(config)
    case_dir = tmp_path / "case"
    generate_openfoam_case(config, bundle, case_dir)

    fv_solution = (case_dir / "system" / "fvSolution").read_text(encoding="utf-8")
    assert "consistent yes;" in fv_solution
    assert "p 0.2;" in fv_solution
    assert "U 0.5;" in fv_solution

    control_dict = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    assert "endTime         3000;" in control_dict


def test_generated_case_records_problem_provenance_and_mesh_refinement(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    candidate = tmp_path / "candidate.stl"
    _box(candidate, (0.25, 0.0, -0.2), (0.3, 0.3, 0.05))

    config = problem_spec_to_project_config(spec, candidate_stl=candidate, voxel_size_m=0.1)
    bundle = build_fields(config)
    case_dir = tmp_path / "case"
    summary = generate_openfoam_case(config, bundle, case_dir)

    assert summary.force_patches == ["design_candidate"]
    metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
    assert metadata["problem_id"] == "adapter_fixture"
    assert metadata["problem_spec_sha256"] == problem_spec_sha256(spec)
    assert metadata["flow_case_id"] == "straight"
    # 0.1 (not 0.15) because a declared grid.domain_bounds_m (WP1/P17) requires the
    # Stage V voxel to divide the fixed extents on every axis; 0.15 does not divide 1.6.
    assert metadata["mesh_refinement"]["voxel_size_m"] == pytest.approx(0.1)
    background = metadata["mesh_refinement"]["background_block_mesh_cells"]
    assert background["total"] == background["nx"] * background["ny"] * background["nz"]

    candidate_entry = next(
        item for item in metadata["tri_surface_files"] if item["role"] == "design"
    )
    assert candidate_entry["source_path"] == str(candidate.resolve())
    import hashlib

    assert candidate_entry["sha256"] == hashlib.sha256(candidate.read_bytes()).hexdigest()

    reference = metadata["force_reference"]
    assert reference["area_m2"] == pytest.approx(1.2)
    assert reference["length_m"] == pytest.approx(0.8)


def test_extra_refinement_regions_render_searchable_boxes(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))
    candidate = tmp_path / "candidate.stl"
    _box(candidate, (0.25, 0.0, -0.2), (0.3, 0.3, 0.05))
    config = problem_spec_to_project_config(spec, candidate_stl=candidate, voxel_size_m=0.1)
    bundle = build_fields(config)
    case_dir = tmp_path / "case"

    generate_openfoam_case(config, bundle, tmp_path / "case_plain")
    plain = (tmp_path / "case_plain" / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
    assert "searchableBox" not in plain

    summary = generate_openfoam_case(
        config,
        bundle,
        case_dir,
        extra_refinement_regions=[((0.0, -0.3, -0.2), (0.6, 0.3, 0.3), 2)],
    )
    snappy = (case_dir / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
    assert "type searchableBox;" in snappy
    assert "min (0 -0.3 -0.2);" in snappy
    assert "max (0.6 0.3 0.3);" in snappy
    assert "mode inside;" in snappy
    assert "levels ((1E15 2));" in snappy
    import json as _json
    meta = _json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
    assert meta["extra_refinement_regions"] == [
        {"box_m": {"min": [0.0, -0.3, -0.2], "max": [0.6, 0.3, 0.3]}, "refinement_level": 2}
    ]
    assert summary.force_patches == ["design_candidate"]


def test_voxel_size_override_changes_background_cell_count(tmp_path: Path) -> None:
    spec = load_problem_spec(_write_spec(tmp_path))

    coarse_config = problem_spec_to_project_config(spec, voxel_size_m=0.2)
    fine_config = problem_spec_to_project_config(spec, voxel_size_m=0.05)
    coarse_bundle = build_fields(coarse_config)
    fine_bundle = build_fields(fine_config)

    coarse_summary = generate_openfoam_case(coarse_config, coarse_bundle, tmp_path / "coarse")
    fine_summary = generate_openfoam_case(fine_config, fine_bundle, tmp_path / "fine")

    coarse_meta = json.loads(
        (tmp_path / "coarse" / "case_metadata.json").read_text(encoding="utf-8")
    )["mesh_refinement"]["background_block_mesh_cells"]["total"]
    fine_meta = json.loads(
        (tmp_path / "fine" / "case_metadata.json").read_text(encoding="utf-8")
    )["mesh_refinement"]["background_block_mesh_cells"]["total"]
    assert fine_meta > coarse_meta
    assert coarse_summary.stl_count == fine_summary.stl_count
