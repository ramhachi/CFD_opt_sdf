from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from cfd_sdf.openfoam_case_renderer import (
    openfoam_retained_field_boundary_specs,
    render_openfoam_physics_files,
)
from cfd_sdf.solver_case_manifest import SolverFlowCasePlan


def _plan(*, turbulence: str = "laminar") -> SolverFlowCasePlan:
    requested_boundaries = {
        "inlet": "freestream",
        "outlet": "pressure_outlet",
        "side": "symmetry",
        "ground": "moving_wall",
    }
    generated_boundaries = {
        "inlet": {
            "patch_type": "patch",
            "U": {"type": "fixedValue", "value": (30.0, 0.0, 0.0)},
            "p": {"type": "zeroGradient"},
        },
        "outlet": {
            "patch_type": "patch",
            "U": {"type": "zeroGradient"},
            "p": {"type": "fixedValue", "value": 0.0},
        },
        "side": {
            "patch_type": "symmetryPlane",
            "U": {"type": "symmetryPlane"},
            "p": {"type": "symmetryPlane"},
        },
        "ground": {
            "patch_type": "wall",
            "U": {"type": "fixedValue", "value": (30.0, 0.0, 0.0)},
            "p": {"type": "zeroGradient"},
            "motion_profile_id": "moving_ground",
        },
    }
    turbulence_generated = {
        "model": turbulence,
        "k_m2_s2": None,
        "omega_s_inv": None,
    }
    if turbulence == "k_omega_sst":
        turbulence_generated.update(k_m2_s2=3.375, omega_s_inv=16.7705098312)
    return SolverFlowCasePlan(
        flow_case_id="straight",
        case_directory_name="flow_straight",
        requested={
            "freestream_velocity_mps": (30.0, 0.0, 0.0),
            "boundary_conditions": requested_boundaries,
            "motion_profiles": {
                "moving_ground": {
                    "kind": "translation",
                    "boundary_ids": ("ground",),
                    "velocity_mps": (30.0, 0.0, 0.0),
                }
            },
            "response_ids": ("straight_force",),
        },
        generated={
            "freestream_velocity_mps": (30.0, 0.0, 0.0),
            "speed_mps": 30.0,
            "fluid": {"kinematic_viscosity_m2_s": 1.8e-5 / 1.225},
            "turbulence": turbulence_generated,
            "boundary_conditions": generated_boundaries,
            "responses": ({"response_id": "straight_force"},),
        },
        supported_response_ids=("straight_force",),
        unsupported=(),
    )


def _replace_plan(plan: SolverFlowCasePlan, **updates) -> SolverFlowCasePlan:
    values = {
        "flow_case_id": plan.flow_case_id,
        "case_directory_name": plan.case_directory_name,
        "requested": deepcopy(plan.requested),
        "generated": deepcopy(plan.generated),
        "supported_response_ids": plan.supported_response_ids,
        "unsupported": plan.unsupported,
    }
    values.update(updates)
    return SolverFlowCasePlan(**values)


def test_laminar_renders_exact_physics_and_boundary_files(tmp_path: Path) -> None:
    artifacts = render_openfoam_physics_files(_plan(), tmp_path / "case")

    transport = artifacts.transport_properties.read_text(encoding="utf-8")
    turbulence = artifacts.turbulence_properties.read_text(encoding="utf-8")
    velocity = artifacts.velocity_field.read_text(encoding="utf-8")
    pressure = artifacts.pressure_field.read_text(encoding="utf-8")
    assert "transportModel  Newtonian;" in transport
    assert "nu              [0 2 -1 0 0 0 0] 1.4693877551e-05;" in transport
    assert turbulence.endswith("simulationType laminar;\n")
    assert "internalField   uniform (30 0 0);" in velocity
    assert "    inlet\n    {\n        type            fixedValue;\n        value" in velocity
    assert "    outlet\n    {\n        type            zeroGradient;" in velocity
    assert "    side\n    {\n        type            symmetryPlane;" in velocity
    assert "    ground\n    {\n        type            fixedValue;\n        value" in velocity
    assert "    outlet\n    {\n        type            fixedValue;\n        value           uniform 0;" in pressure
    assert artifacts.turbulent_kinetic_energy_field is None
    assert artifacts.adjoint_turbulent_kinetic_energy_field is None
    assert artifacts.adjoint_specific_dissipation_rate_field is None
    assert "adjointRASModel      adjointLaminar;" in artifacts.adjoint_turbulence_properties.read_text(
        encoding="utf-8"
    )
    assert "adjointTurbulence   off;" in artifacts.adjoint_turbulence_properties.read_text(
        encoding="utf-8"
    )
    assert "default           steadyState;" in artifacts.fv_schemes.read_text(encoding="utf-8")
    assert "default           Gauss linear;" in artifacts.fv_schemes.read_text(encoding="utf-8")
    assert "div((nuEff*dev2(T(grad(U))))) Gauss linear;" in artifacts.fv_schemes.read_text(
        encoding="utf-8"
    )
    assert "div(-phi,Ua)      bounded Gauss linearUpwind grad(Ua);" in artifacts.fv_schemes.read_text(
        encoding="utf-8"
    )
    mass_dict = artifacts.normalized_mass_imbalance_function_dict.read_text(encoding="utf-8")
    assert "cfdSdfMassSigned0" in mass_dict
    assert "cfdSdfMassMagnitude1" in mass_dict
    assert "name            inlet;" in mass_dict
    assert "name            outlet;" in mass_dict
    physics_metadata = json.loads(artifacts.metadata_json.read_text(encoding="utf-8"))
    assert physics_metadata["normalized_mass_imbalance"]["open_patch_ids"] == [
        "inlet",
        "outlet",
    ]
    assert '"(U|Ua.*|yWall|da)"' in artifacts.fv_solution.read_text(encoding="utf-8")
    assert '"(k|ka.*|omega|wa.*)"' not in artifacts.fv_solution.read_text(encoding="utf-8")
    assert not (tmp_path / "case/0.orig/k").exists()
    assert not (tmp_path / "case/0.orig/ka").exists()
    assert b"\r\n" not in artifacts.velocity_field.read_bytes()


def test_sst_renders_k_omega_nut_and_wall_functions(tmp_path: Path) -> None:
    artifacts = render_openfoam_physics_files(_plan(turbulence="k_omega_sst"), tmp_path / "sst")

    assert "simulationType RAS;" in artifacts.turbulence_properties.read_text(encoding="utf-8")
    assert "RASModel        kOmegaSST;" in artifacts.turbulence_properties.read_text(encoding="utf-8")
    k_text = artifacts.turbulent_kinetic_energy_field.read_text(encoding="utf-8")
    omega_text = artifacts.specific_dissipation_rate_field.read_text(encoding="utf-8")
    nut_text = artifacts.turbulent_viscosity_field.read_text(encoding="utf-8")
    assert "internalField   uniform 3.375;" in k_text
    assert "internalField   uniform 16.7705098312;" in omega_text
    assert "type            fixedValue;" in k_text
    assert "type            zeroGradient;" in k_text
    assert "type            kqRWallFunction;" in k_text
    assert "type            omegaWallFunction;" in omega_text
    assert "type            nutkWallFunction;" in nut_text
    assert "type            symmetryPlane;" in nut_text
    assert "type            calculated;" in nut_text
    assert "type            zeroGradient;" in nut_text
    ka_text = artifacts.adjoint_turbulent_kinetic_energy_field.read_text(encoding="utf-8")
    wa_text = artifacts.adjoint_specific_dissipation_rate_field.read_text(encoding="utf-8")
    assert "dimensions      [0 0 0 0 0 0 0];" in ka_text
    assert "dimensions      [0 2 -1 0 0 0 0];" in wa_text
    assert "internalField   uniform 0;" in ka_text
    assert "type            adjointZeroInlet;" in ka_text
    assert "type            adjointOutletKa;" in ka_text
    assert "type            adjointOutletWa;" in wa_text
    assert "type            kaqRWallFunction;" in ka_text
    assert "type            waWallFunction;" in wa_text
    adjoint_properties = artifacts.adjoint_turbulence_properties.read_text(encoding="utf-8")
    assert "object      adjointTurbulenceProperties;" in adjoint_properties
    assert "adjointRASModel      adjointkOmegaSST;" in adjoint_properties
    assert "adjointTurbulence   on;" in adjoint_properties
    schemes = artifacts.fv_schemes.read_text(encoding="utf-8")
    for token in (
        "grad(U)",
        "grad(k)",
        "grad(omega)",
        "grad(Ua)",
        "grad(ka)",
        "grad(wa)",
        "div(phi,U)",
        "div(phi,k)",
        "div(phi,omega)",
        "div(phia,Ua)",
        "div(-phi,Ua)",
        "div(-phi,ka)",
        "div(-phi,wa)",
        "method            meshWave;",
    ):
        assert token in schemes
    solution = artifacts.fv_solution.read_text(encoding="utf-8")
    assert "    p\n    {\n        solver          PCG;\n        preconditioner  DIC;\n        tolerance       1e-9;\n        relTol          0.01;\n    }" in solution
    assert '"(U|yWall|da|k|omega)"' in solution
    assert "        relTol          0.1;" in solution
    assert '"(p|pa.*)"' not in solution
    assert '"(U|Ua.*|yWall|da|k|ka.*|omega|wa.*)"' not in solution
    assert "    \"pa.*\"\n    {\n        solver          PCG;\n        preconditioner  DIC;\n        tolerance       1e-9;\n        relTol          0;\n    }" in solution
    for field_name in ("Ua.*", "ka.*", "wa.*"):
        assert (
            f"    \"{field_name}\"\n"
            "    {\n"
            "        solver          PBiCGStab;\n"
            "        preconditioner  DILU;\n"
            "        tolerance       1e-9;\n"
            "        relTol          0;\n"
            "    }"
        ) in solution
    assert '"pa.*" 0.5;' in solution
    metadata = json.loads(artifacts.metadata_json.read_text(encoding="utf-8"))
    assert metadata["generated"]["wall_distance"] == {
        "method": "meshWave",
        "porous_aware": False,
        "qualification": "not_qualified",
    }
    for relative in (
        "constant/adjointRASProperties",
        "system/fvSchemes",
        "system/fvSolution",
        "0.orig/ka",
        "0.orig/wa",
    ):
        assert relative in metadata["generated_files"]
        assert relative in artifacts.file_sha256


def test_moving_wall_velocity_is_rendered_from_generated_plan(tmp_path: Path) -> None:
    plan = _plan()
    plan.generated["boundary_conditions"]["ground"]["U"]["value"] = (12.0, 1.0, 0.0)

    artifacts = render_openfoam_physics_files(plan, tmp_path / "moving")
    text = artifacts.velocity_field.read_text(encoding="utf-8")
    ground = text.split("    ground", 1)[1]
    assert "value           uniform (12 1 0);" in ground


def test_retained_field_boundary_policy_maps_moving_wall_to_wall_types() -> None:
    specs = openfoam_retained_field_boundary_specs(_plan())

    assert specs["alpha"]["ground"] == {"type": "zeroGradient"}
    assert specs["Ua"]["ground"] == {
        "type": "adjointWallVelocity",
        "value": (0.0, 0.0, 0.0),
    }
    assert specs["pa"]["ground"] == {"type": "zeroGradient"}
    assert specs["alpha"]["outlet"] == {"type": "fixedValue", "value": 0.0}
    assert specs["Ua"]["side"] == {"type": "symmetryPlane"}


def test_v2512_topology_regularisation_renders_explicit_b_tilda_solver(
    tmp_path: Path,
) -> None:
    artifacts = render_openfoam_physics_files(
        _plan(),
        tmp_path / "b_tilda",
        fv_solution_initialization_solver_fields=("bTilda",),
    )

    solution = artifacts.fv_solution.read_text(encoding="utf-8")
    assert "    bTilda\n    {" in solution
    assert "        solver          PCG;" in solution
    assert "        preconditioner  DIC;" in solution
    assert artifacts.fv_solution_initialization_solver_fields == ("bTilda",)
    metadata = json.loads(artifacts.metadata_json.read_text(encoding="utf-8"))
    assert metadata["fv_solution"] == {
        "openfoam_version": "v2512",
        "initialization_solver_fields": ["bTilda"],
    }


@pytest.mark.parametrize("fields", [("unknown",), "bTilda"])
def test_unknown_or_scalar_fv_solution_initialization_fields_are_rejected(
    tmp_path: Path, fields
) -> None:
    with pytest.raises(ValueError, match="fvSolution initialization solver field"):
        render_openfoam_physics_files(
            _plan(),
            tmp_path / "invalid_initialization_fields",
            fv_solution_initialization_solver_fields=fields,
        )


def test_metadata_hashes_match_generated_file_readback(tmp_path: Path) -> None:
    artifacts = render_openfoam_physics_files(_plan(), tmp_path / "hashes")
    metadata = json.loads(artifacts.metadata_json.read_text(encoding="utf-8"))

    assert metadata["requested"]["boundary_conditions"]["ground"] == "moving_wall"
    assert metadata["generated"]["speed_mps"] == pytest.approx(30.0)
    for relative, record in metadata["generated_files"].items():
        content = (artifacts.case_dir / relative).read_bytes()
        assert hashlib.sha256(content).hexdigest() == record["sha256"]
        assert len(content) == record["size_bytes"]
        assert artifacts.file_sha256[relative] == record["sha256"]


def test_plan_with_unsupported_features_is_rejected(tmp_path: Path) -> None:
    plan = _replace_plan(_plan(), unsupported=("unsupported_response_kind:pitch:moment",))

    with pytest.raises(ValueError, match="unsupported features"):
        render_openfoam_physics_files(plan, tmp_path / "unsupported")


@pytest.mark.parametrize(
    ("field", "bad_id"),
    [("patch", "../inlet"), ("response", "bad/response"), ("generated_response", "bad/path")],
)
def test_unsafe_patch_and_response_ids_are_rejected(
    tmp_path: Path, field: str, bad_id: str
) -> None:
    plan = _plan()
    if field == "patch":
        plan.generated["boundary_conditions"][bad_id] = plan.generated["boundary_conditions"].pop("inlet")
        plan.requested["boundary_conditions"][bad_id] = plan.requested["boundary_conditions"].pop("inlet")
    elif field == "response":
        plan = _replace_plan(plan, supported_response_ids=(bad_id,))
    else:
        plan.generated["responses"][0]["response_id"] = bad_id

    with pytest.raises(ValueError, match="Unsafe"):
        render_openfoam_physics_files(plan, tmp_path / f"unsafe_{field}")


@pytest.mark.parametrize("patch_id", ["spanMin", "outlet-right"])
def test_openfoam_patch_ids_allow_safe_camelcase_and_hyphen(
    tmp_path: Path, patch_id: str
) -> None:
    plan = _plan()
    plan.generated["boundary_conditions"][patch_id] = plan.generated[
        "boundary_conditions"
    ].pop("side")
    plan.requested["boundary_conditions"][patch_id] = plan.requested[
        "boundary_conditions"
    ].pop("side")

    artifacts = render_openfoam_physics_files(plan, tmp_path / f"safe_{patch_id}")
    assert f"    {patch_id}\n" in artifacts.velocity_field.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "patch_id", ["has space", "bad{patch", "bad}patch", "bad;patch", "bad/patch", 'bad"patch']
)
def test_openfoam_patch_ids_reject_injection_characters(
    tmp_path: Path, patch_id: str
) -> None:
    plan = _plan()
    plan.generated["boundary_conditions"][patch_id] = plan.generated[
        "boundary_conditions"
    ].pop("side")
    plan.requested["boundary_conditions"][patch_id] = plan.requested[
        "boundary_conditions"
    ].pop("side")

    with pytest.raises(ValueError, match="Unsafe boundary patch_id"):
        render_openfoam_physics_files(plan, tmp_path / "unsafe_patch")


def test_non_marker_nonempty_directory_is_never_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "foreign"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("owned elsewhere", encoding="utf-8")

    for overwrite in (False, True):
        with pytest.raises(FileExistsError, match="without generated_openfoam_physics.json"):
            render_openfoam_physics_files(_plan(), target, overwrite=overwrite)
    assert sentinel.read_text(encoding="utf-8") == "owned elsewhere"


def test_marker_directory_requires_overwrite_and_can_be_safely_updated(tmp_path: Path) -> None:
    target = tmp_path / "owned"
    first = render_openfoam_physics_files(_plan(), target)
    with pytest.raises(FileExistsError, match="overwrite=True"):
        render_openfoam_physics_files(_plan(), target)

    updated = _plan()
    updated.generated["freestream_velocity_mps"] = (31.0, 0.0, 0.0)
    second = render_openfoam_physics_files(updated, target, overwrite=True)
    assert first.metadata_json == second.metadata_json
    assert "internalField   uniform (31 0 0);" in second.velocity_field.read_text(encoding="utf-8")


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_values_are_rejected_without_writing_nan_or_inf(
    tmp_path: Path, bad_value: float
) -> None:
    plan = _plan()
    plan.generated["fluid"]["kinematic_viscosity_m2_s"] = bad_value
    target = tmp_path / "nonfinite"

    with pytest.raises(ValueError, match="finite number"):
        render_openfoam_physics_files(plan, target)
    assert not (target / "constant/transportProperties").exists()


def test_missing_generated_fields_are_rejected(tmp_path: Path) -> None:
    plan = _plan()
    del plan.generated["fluid"]["kinematic_viscosity_m2_s"]

    with pytest.raises(ValueError, match="kinematic_viscosity_m2_s"):
        render_openfoam_physics_files(plan, tmp_path / "missing")
