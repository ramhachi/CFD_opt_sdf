"""Render deterministic OpenFOAM physics dictionaries from a solver flow plan."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

from .openfoam_mass_imbalance import (
    normalized_mass_imbalance_contract,
    render_openfoam_mass_imbalance_function_dict,
)
from .solver_case_manifest import SolverFlowCasePlan


_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PATCH_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_MARKER_NAME = "generated_openfoam_physics.json"


# ``adjointOptimisationFoam`` v2512 constructs this temporary field while
# initialising a regularised ``topO`` design.  It is deliberately an explicit
# entry rather than being folded into the pressure regex: the Helmholtz
# equation is symmetric positive definite and the stock v2512 topology
# tutorial uses PCG/DIC for it.  The compiler only requests it after auditing
# ``optimisationDict``; callers cannot inject arbitrary fvSolution snippets.
_OPENFOAM_V2512_INITIALIZATION_SOLVERS = {
    "bTilda": (
        "    bTilda\n"
        "    {\n"
        "        solver          PCG;\n"
        "        preconditioner  DIC;\n"
        "        tolerance       1e-9;\n"
        "        relTol          0.1;\n"
        "    }\n"
    ),
}


# These fields are supplied by the topology-optimisation template rather than
# rendered as wholly new fields.  Their boundary types still have to follow the
# compiled mesh patch type.  The wall choices mirror the OpenFOAM v2512
# porosity-based topology-optimisation tutorial: alpha/pa use zeroGradient and
# Ua uses adjointWallVelocity with a zero value.
_RETAINED_FIELD_BOUNDARY_SPECS = {
    "freestream": {
        "alpha": {"type": "zeroGradient"},
        "Ua": {"type": "adjointInletVelocity", "value": (0.0, 0.0, 0.0)},
        "pa": {"type": "zeroGradient"},
    },
    "pressure_outlet": {
        "alpha": {"type": "fixedValue", "value": 0.0},
        "Ua": {"type": "adjointOutletVelocity", "value": (0.0, 0.0, 0.0)},
        "pa": {"type": "adjointOutletPressure", "value": 0.0},
    },
    "symmetry": {
        "alpha": {"type": "symmetryPlane"},
        "Ua": {"type": "symmetryPlane"},
        "pa": {"type": "symmetryPlane"},
    },
    "stationary_wall": {
        "alpha": {"type": "zeroGradient"},
        "Ua": {"type": "adjointWallVelocity", "value": (0.0, 0.0, 0.0)},
        "pa": {"type": "zeroGradient"},
    },
    "moving_wall": {
        "alpha": {"type": "zeroGradient"},
        "Ua": {"type": "adjointWallVelocity", "value": (0.0, 0.0, 0.0)},
        "pa": {"type": "zeroGradient"},
    },
}


@dataclass(frozen=True)
class OpenFOAMPhysicsArtifacts:
    case_dir: Path
    transport_properties: Path
    turbulence_properties: Path
    adjoint_turbulence_properties: Path
    fv_schemes: Path
    fv_solution: Path
    normalized_mass_imbalance_function_dict: Path
    fv_solution_initialization_solver_fields: tuple[str, ...]
    velocity_field: Path
    pressure_field: Path
    turbulent_kinetic_energy_field: Path | None
    specific_dissipation_rate_field: Path | None
    turbulent_viscosity_field: Path | None
    adjoint_turbulent_kinetic_energy_field: Path | None
    adjoint_specific_dissipation_rate_field: Path | None
    metadata_json: Path
    file_sha256: Mapping[str, str]


def openfoam_retained_field_boundary_specs(
    plan: SolverFlowCasePlan,
) -> Mapping[str, Mapping[str, Mapping[str, Any]]]:
    """Return compiler-owned boundary policies for retained template fields.

    ``alpha``, ``Ua``, and ``pa`` stay template-owned because they may carry
    topology initialisation or solver-specific settings.  Their boundary
    entries are nevertheless derived from the manifest so a converted wall
    mesh patch cannot retain an incompatible ``symmetryPlane`` field entry.
    """

    requested = _mapping(plan.requested, "requested")
    generated = _mapping(plan.generated, "generated")
    requested_boundaries = _mapping(
        requested.get("boundary_conditions"), "requested.boundary_conditions"
    )
    generated_boundaries = _mapping(
        generated.get("boundary_conditions"), "generated.boundary_conditions"
    )
    if set(requested_boundaries) != set(generated_boundaries):
        raise ValueError("Generated and requested boundary patch sets must match exactly")

    fields: dict[str, dict[str, Mapping[str, Any]]] = {
        "alpha": {},
        "Ua": {},
        "pa": {},
    }
    for raw_patch_id, raw_kind in requested_boundaries.items():
        patch_id = str(raw_patch_id)
        _validate_patch_id(patch_id)
        if not isinstance(raw_kind, str) or raw_kind not in _RETAINED_FIELD_BOUNDARY_SPECS:
            raise ValueError(f"Unsupported retained-field boundary kind: {raw_kind!r}")
        generated_spec = _mapping(
            generated_boundaries.get(raw_patch_id), f"generated.boundary_conditions.{patch_id}"
        )
        expected_patch_type = "symmetryPlane" if raw_kind == "symmetry" else (
            "wall" if raw_kind in {"stationary_wall", "moving_wall"} else "patch"
        )
        if generated_spec.get("patch_type") != expected_patch_type:
            raise ValueError(
                f"Generated patch type does not match retained-field boundary kind: {patch_id}"
            )
        for field_name, spec in _RETAINED_FIELD_BOUNDARY_SPECS[raw_kind].items():
            fields[field_name][patch_id] = MappingProxyType(dict(spec))
    return MappingProxyType(
        {
            field_name: MappingProxyType(dict(specs))
            for field_name, specs in fields.items()
        }
    )


def render_openfoam_physics_files(
    plan: SolverFlowCasePlan,
    case_dir: str | Path,
    *,
    overwrite: bool = False,
    fv_solution_initialization_solver_fields: Sequence[str] = (),
) -> OpenFOAMPhysicsArtifacts:
    """Write only compiler-owned OpenFOAM physics files into ``case_dir``."""

    if plan.unsupported:
        raise ValueError(f"Cannot render a flow plan with unsupported features: {plan.unsupported!r}")
    _validate_id(plan.flow_case_id, "flow_case_id")
    for response_id in plan.supported_response_ids:
        _validate_id(response_id, "supported response_id")

    target = Path(case_dir)
    marker = target / _MARKER_NAME
    if target.exists() and any(target.iterdir()):
        if not marker.is_file():
            raise FileExistsError(
                f"Refusing to write non-empty case directory without {_MARKER_NAME}: {target}"
            )
        if not overwrite:
            raise FileExistsError(f"Generated case already exists; use overwrite=True: {target}")
    target.mkdir(parents=True, exist_ok=True)

    initialization_solver_fields = _normalize_fv_solution_initialization_solver_fields(
        fv_solution_initialization_solver_fields
    )
    generated = _mapping(plan.generated, "generated")
    requested = _mapping(plan.requested, "requested")
    _validate_response_bindings(plan, requested, generated)
    velocity = _vector3(generated.get("freestream_velocity_mps"), "generated.freestream_velocity_mps")
    fluid = _mapping(generated.get("fluid"), "generated.fluid")
    nu = _number(fluid.get("kinematic_viscosity_m2_s"), "generated.fluid.kinematic_viscosity_m2_s")
    if nu <= 0.0:
        raise ValueError("generated.fluid.kinematic_viscosity_m2_s must be positive")
    turbulence = _mapping(generated.get("turbulence"), "generated.turbulence")
    model = turbulence.get("model")
    if model not in {"laminar", "k_omega_sst"}:
        raise ValueError(f"Unsupported generated turbulence model: {model!r}")
    boundaries = _mapping(generated.get("boundary_conditions"), "generated.boundary_conditions")
    requested_boundaries = _mapping(
        requested.get("boundary_conditions"), "requested.boundary_conditions"
    )
    if set(boundaries) != set(requested_boundaries):
        raise ValueError("Generated and requested boundary patch sets must match exactly")
    for patch_id in boundaries:
        _validate_patch_id(str(patch_id))
    open_patch_ids = tuple(
        sorted(
            str(patch_id)
            for patch_id, kind in requested_boundaries.items()
            if kind in {"freestream", "pressure_outlet"}
        )
    )
    if not open_patch_ids:
        raise ValueError("A flow case needs at least one freestream or pressure_outlet patch")

    texts: dict[str, str] = {
        "constant/transportProperties": _transport_properties(nu),
        "constant/turbulenceProperties": _turbulence_properties(str(model)),
        "constant/adjointRASProperties": _adjoint_turbulence_properties(str(model)),
        "system/fvSchemes": _fv_schemes(str(model)),
        "system/fvSolution": _fv_solution(
            str(model),
            initialization_solver_fields=initialization_solver_fields,
        ),
        "system/cfdSdfMassImbalanceDict": render_openfoam_mass_imbalance_function_dict(
            open_patch_ids
        ),
        "0.orig/U": _field_text(
            name="U",
            field_class="volVectorField",
            dimensions="[0 1 -1 0 0 0 0]",
            internal_value=velocity,
            boundary_specs={
                str(patch): _mapping(_mapping(spec, f"boundary.{patch}").get("U"), f"boundary.{patch}.U")
                for patch, spec in boundaries.items()
            },
        ),
        "0.orig/p": _field_text(
            name="p",
            field_class="volScalarField",
            dimensions="[0 2 -2 0 0 0 0]",
            internal_value=0.0,
            boundary_specs={
                str(patch): _mapping(_mapping(spec, f"boundary.{patch}").get("p"), f"boundary.{patch}.p")
                for patch, spec in boundaries.items()
            },
        ),
    }

    k_path: Path | None = None
    omega_path: Path | None = None
    nut_path: Path | None = None
    ka_path: Path | None = None
    wa_path: Path | None = None
    if model == "k_omega_sst":
        k = _number(turbulence.get("k_m2_s2"), "generated.turbulence.k_m2_s2")
        omega = _number(turbulence.get("omega_s_inv"), "generated.turbulence.omega_s_inv")
        if k <= 0.0 or omega <= 0.0:
            raise ValueError("SST k and omega must be positive")
        sst_specs = _sst_boundary_specs(requested_boundaries, k, omega)
        texts["0.orig/k"] = _field_text(
            name="k",
            field_class="volScalarField",
            dimensions="[0 2 -2 0 0 0 0]",
            internal_value=k,
            boundary_specs={patch: specs["k"] for patch, specs in sst_specs.items()},
        )
        texts["0.orig/omega"] = _field_text(
            name="omega",
            field_class="volScalarField",
            dimensions="[0 0 -1 0 0 0 0]",
            internal_value=omega,
            boundary_specs={patch: specs["omega"] for patch, specs in sst_specs.items()},
        )
        texts["0.orig/nut"] = _field_text(
            name="nut",
            field_class="volScalarField",
            dimensions="[0 2 -1 0 0 0 0]",
            internal_value=0.0,
            boundary_specs={patch: specs["nut"] for patch, specs in sst_specs.items()},
        )
        adjoint_specs = _adjoint_sst_boundary_specs(requested_boundaries)
        texts["0.orig/ka"] = _field_text(
            name="ka",
            field_class="volScalarField",
            dimensions="[0 0 0 0 0 0 0]",
            internal_value=0.0,
            boundary_specs={patch: specs["ka"] for patch, specs in adjoint_specs.items()},
        )
        texts["0.orig/wa"] = _field_text(
            name="wa",
            field_class="volScalarField",
            dimensions="[0 2 -1 0 0 0 0]",
            internal_value=0.0,
            boundary_specs={patch: specs["wa"] for patch, specs in adjoint_specs.items()},
        )

    hashes: dict[str, str] = {}
    for relative, text in texts.items():
        if "nan" in text.lower() or "inf" in text.lower():
            raise ValueError(f"Refusing to write non-finite OpenFOAM file: {relative}")
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        hashes[relative] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    generated_snapshot = _json_copy(plan.generated)
    if model == "k_omega_sst":
        generated_snapshot["wall_distance"] = {
            "method": "meshWave",
            "porous_aware": False,
            "qualification": "not_qualified",
        }
    metadata = {
        "schema_version": 1,
        "kind": "generated_openfoam_physics",
        "flow_case_id": plan.flow_case_id,
        "case_directory_name": plan.case_directory_name,
        "requested": _json_copy(plan.requested),
        "generated": generated_snapshot,
        "fv_solution": {
            "openfoam_version": "v2512",
            "initialization_solver_fields": list(initialization_solver_fields),
        },
        "normalized_mass_imbalance": normalized_mass_imbalance_contract(open_patch_ids),
        "generated_files": {
            relative: {
                "sha256": digest,
                "size_bytes": len(texts[relative].encode("utf-8")),
            }
            for relative, digest in sorted(hashes.items())
        },
    }
    marker.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    if "0.orig/k" in texts:
        k_path = target / "0.orig/k"
        omega_path = target / "0.orig/omega"
        nut_path = target / "0.orig/nut"
        ka_path = target / "0.orig/ka"
        wa_path = target / "0.orig/wa"
    return OpenFOAMPhysicsArtifacts(
        case_dir=target,
        transport_properties=target / "constant/transportProperties",
        turbulence_properties=target / "constant/turbulenceProperties",
        adjoint_turbulence_properties=target / "constant/adjointRASProperties",
        fv_schemes=target / "system/fvSchemes",
        fv_solution=target / "system/fvSolution",
        normalized_mass_imbalance_function_dict=target / "system/cfdSdfMassImbalanceDict",
        fv_solution_initialization_solver_fields=initialization_solver_fields,
        velocity_field=target / "0.orig/U",
        pressure_field=target / "0.orig/p",
        turbulent_kinetic_energy_field=k_path,
        specific_dissipation_rate_field=omega_path,
        turbulent_viscosity_field=nut_path,
        adjoint_turbulent_kinetic_energy_field=ka_path,
        adjoint_specific_dissipation_rate_field=wa_path,
        metadata_json=marker,
        file_sha256=MappingProxyType(dict(hashes)),
    )


def _transport_properties(nu: float) -> str:
    return _dictionary_header("transportProperties") + (
        "transportModel  Newtonian;\n\n"
        f"nu              [0 2 -1 0 0 0 0] {_format_number(nu)};\n"
    )


def _turbulence_properties(model: str) -> str:
    if model == "laminar":
        body = "simulationType laminar;\n"
    else:
        body = (
            "simulationType RAS;\n\n"
            "RAS\n"
            "{\n"
            "    RASModel        kOmegaSST;\n"
            "    turbulence      on;\n"
            "    printCoeffs     on;\n"
            "}\n"
        )
    return _dictionary_header("turbulenceProperties") + body


def _adjoint_turbulence_properties(model: str) -> str:
    adjoint_model = "adjointLaminar" if model == "laminar" else "adjointkOmegaSST"
    enabled = "off" if model == "laminar" else "on"
    return _dictionary_header("adjointTurbulenceProperties") + (
        f"adjointRASModel      {adjoint_model};\n"
        f"adjointTurbulence   {enabled};\n"
        "printCoeffs          on;\n"
    )


def _fv_schemes(model: str) -> str:
    turbulence_grads = ""
    turbulence_divs = ""
    if model == "k_omega_sst":
        turbulence_grads = (
            "    grad(k)         Gauss linear;\n"
            "    grad(omega)     Gauss linear;\n"
            "    grad(ka)        Gauss linear;\n"
            "    grad(wa)        Gauss linear;\n"
        )
        turbulence_divs = (
            "    div(phi,k)      bounded Gauss upwind;\n"
            "    div(phi,omega)  bounded Gauss upwind;\n"
            # The adjoint transport equations use the reverse primal flux.
            # This is the v2512 kOmegaSST tutorial form (with the generated
            # field names substituted for the tutorial's ``ka``/``wa``).
            "    div(-phi,ka)    bounded Gauss linearUpwind grad(ka);\n"
            "    div(-phi,wa)    bounded Gauss linearUpwind grad(wa);\n"
        )
    return _dictionary_header("fvSchemes") + (
        "ddtSchemes\n"
        "{\n"
        "    default           steadyState;\n"
        "}\n\n"
        "gradSchemes\n"
        "{\n"
        "    default           cellLimited Gauss linear 1;\n"
        "    grad(U)           Gauss linear;\n"
        "    grad(Ua)          Gauss linear;\n"
        f"{turbulence_grads}"
        "}\n\n"
        "divSchemes\n"
        "{\n"
        "    default           Gauss linear;\n"
        "    div(phi,U)        bounded Gauss linearUpwind grad(U);\n"
        "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n"
        "    div(phia,Ua)      bounded Gauss linearUpwind grad(Ua);\n"
        "    div(-phi,Ua)      bounded Gauss linearUpwind grad(Ua);\n"
        "    div(-phia,U)      Gauss linearUpwind grad(U);\n"
        f"{turbulence_divs}"
        "}\n\n"
        "laplacianSchemes\n"
        "{\n"
        "    default           Gauss linear corrected;\n"
        "}\n\n"
        "interpolationSchemes\n"
        "{\n"
        "    default           linear;\n"
        "}\n\n"
        "snGradSchemes\n"
        "{\n"
        "    default           corrected;\n"
        "}\n\n"
        "wallDist\n"
        "{\n"
        "    method            meshWave;\n"
        "}\n"
    )


def _fv_solution(
    model: str, *, initialization_solver_fields: Sequence[str] = ()
) -> str:
    initialization_solvers = "".join(
        _OPENFOAM_V2512_INITIALIZATION_SOLVERS[field_name]
        for field_name in initialization_solver_fields
    )
    pressure_solver = (
        "    \"(p|pa.*)\"\n"
        "    {\n"
        "        solver          GAMG;\n"
        "        tolerance       1e-8;\n"
        "        relTol          0.05;\n"
        "        smoother        GaussSeidel;\n"
        "    }\n"
    )
    velocity_solver = (
        "    \"(U|Ua.*|yWall|da)\"\n"
        "    {\n"
        "        solver          smoothSolver;\n"
        "        smoother        symGaussSeidel;\n"
        "        tolerance       1e-8;\n"
        "        relTol          0.1;\n"
        "    }\n"
    )
    field_relaxation = "        \"(p|pa.*)\" 0.3;\n"
    equation_relaxation = "        \"(U|Ua.*|yWall|da)\" 0.7;\n"
    if model == "k_omega_sst":
        # Match the OpenFOAM v2512 adjointkOmegaSST tutorial's segregated
        # solvers.  GAMG/smoothSolver looked harmless in a short smoke test,
        # but left the nonlinear adjoint residuals at a plateau after 500
        # adjoint iterations.  PCG/DIC and PBiCGStab/DILU are the tutorial's
        # compatible choices for the pressure and coupled velocity/turbulence
        # equations respectively.
        pressure_solver = (
            "    \"(p|pa.*)\"\n"
            "    {\n"
            "        solver          PCG;\n"
            "        preconditioner  DIC;\n"
            "        tolerance       1e-9;\n"
            "        relTol          0.01;\n"
            "    }\n"
        )
        velocity_solver = (
            "    \"(U|Ua.*|yWall|da|k|ka.*|omega|wa.*)\"\n"
            "    {\n"
            "        solver          PBiCGStab;\n"
            "        preconditioner  DILU;\n"
            "        tolerance       1e-9;\n"
            "        relTol          0.1;\n"
            "    }\n"
        )
        field_relaxation = (
            "        p 0.5;\n"
            "        \"pa.*\" 0.5;\n"
        )
        equation_relaxation = (
            "        U 0.7;\n"
            "        \"Ua.*\" 0.7;\n"
            "        \"(k|ka.*|omega|wa.*)\" 0.7;\n"
            "        \"(yWall|da)\" 0.7;\n"
        )
    return _dictionary_header("fvSolution") + (
        "solvers\n"
        "{\n"
        f"{pressure_solver}"
        f"{initialization_solvers}"
        f"{velocity_solver}"
        "}\n\n"
        "SIMPLE\n"
        "{\n"
        "    nNonOrthogonalCorrectors 0;\n"
        "}\n\n"
        "relaxationFactors\n"
        "{\n"
        "    fields\n"
        "    {\n"
        f"{field_relaxation}"
        "    }\n"
        "    equations\n"
        "    {\n"
        f"{equation_relaxation}"
        "    }\n"
        "}\n"
    )


def _normalize_fv_solution_initialization_solver_fields(
    fields: Sequence[str],
) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes, bytearray)):
        raise ValueError("fvSolution initialization solver fields must be a sequence")
    normalized: list[str] = []
    for field_name in fields:
        if not isinstance(field_name, str):
            raise ValueError("fvSolution initialization solver fields must be strings")
        if field_name not in _OPENFOAM_V2512_INITIALIZATION_SOLVERS:
            raise ValueError(
                "Unsupported OpenFOAM v2512 fvSolution initialization solver field: "
                f"{field_name!r}"
            )
        if field_name not in normalized:
            normalized.append(field_name)
    return tuple(normalized)


def _dictionary_header(object_name: str) -> str:
    return (
        "FoamFile\n"
        "{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        "    class       dictionary;\n"
        f"    object      {object_name};\n"
        "}\n\n"
    )


def _field_text(
    *,
    name: str,
    field_class: str,
    dimensions: str,
    internal_value: Any,
    boundary_specs: Mapping[str, Mapping[str, Any]],
) -> str:
    lines = [
        "FoamFile",
        "{",
        "    version     2.0;",
        "    format      ascii;",
        f"    class       {field_class};",
        f"    object      {name};",
        "}",
        "",
        f"dimensions      {dimensions};",
        f"internalField   uniform {_format_value(internal_value)};",
        "",
        "boundaryField",
        "{",
    ]
    for patch_id, spec in boundary_specs.items():
        boundary_type = spec.get("type")
        if not isinstance(boundary_type, str) or not boundary_type:
            raise ValueError(f"Boundary {patch_id!r} is missing a field type")
        lines.extend([f"    {patch_id}", "    {", f"        type            {boundary_type};"])
        for key in ("inletValue", "value"):
            if key in spec:
                lines.append(f"        {key:<15} uniform {_format_value(spec[key])};")
        lines.append("    }")
    lines.extend(["}", ""])
    return "\n".join(lines)


def _sst_boundary_specs(
    requested_boundaries: Mapping[str, Any], k: float, omega: float
) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for patch_id, kind in requested_boundaries.items():
        patch_id = str(patch_id)
        if kind == "freestream":
            result[patch_id] = {
                "k": {"type": "fixedValue", "value": k},
                "omega": {"type": "fixedValue", "value": omega},
                "nut": {"type": "calculated", "value": 0.0},
            }
        elif kind == "pressure_outlet":
            result[patch_id] = {
                "k": {"type": "zeroGradient"},
                "omega": {"type": "zeroGradient"},
                "nut": {"type": "zeroGradient"},
            }
        elif kind == "symmetry":
            result[patch_id] = {
                "k": {"type": "symmetryPlane"},
                "omega": {"type": "symmetryPlane"},
                "nut": {"type": "symmetryPlane"},
            }
        elif kind in {"stationary_wall", "moving_wall"}:
            result[patch_id] = {
                "k": {"type": "kqRWallFunction", "value": 0.0},
                "omega": {"type": "omegaWallFunction", "value": omega},
                "nut": {"type": "nutkWallFunction", "value": 0.0},
            }
        else:
            raise ValueError(f"Unsupported requested SST boundary kind: {kind!r}")
    return result


def _adjoint_sst_boundary_specs(
    requested_boundaries: Mapping[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for patch_id, kind in requested_boundaries.items():
        patch_id = str(patch_id)
        if kind == "freestream":
            result[patch_id] = {
                "ka": {"type": "adjointZeroInlet", "value": 0.0},
                "wa": {"type": "adjointZeroInlet", "value": 0.0},
            }
        elif kind == "pressure_outlet":
            result[patch_id] = {
                "ka": {"type": "adjointOutletKa", "value": 0.0},
                "wa": {"type": "adjointOutletWa", "value": 0.0},
            }
        elif kind == "symmetry":
            result[patch_id] = {
                "ka": {"type": "symmetryPlane"},
                "wa": {"type": "symmetryPlane"},
            }
        elif kind in {"stationary_wall", "moving_wall"}:
            result[patch_id] = {
                "ka": {"type": "kaqRWallFunction", "value": 0.0},
                "wa": {"type": "waWallFunction", "value": 0.0},
            }
        else:
            raise ValueError(f"Unsupported requested adjoint SST boundary kind: {kind!r}")
    return result


def _format_value(value: Any) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) != 3:
            raise ValueError("OpenFOAM vector values must contain exactly three components")
        return "(" + " ".join(_format_number(_number(item, "vector component")) for item in value) + ")"
    return _format_number(_number(value, "scalar value"))


def _format_number(value: float) -> str:
    if not isfinite(value):
        raise ValueError("OpenFOAM values must be finite")
    if value == 0.0:
        return "0"
    return format(value, ".12g")


def _number(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a finite number") from exc
    if not isfinite(result):
        raise ValueError(f"{context} must be a finite number")
    return result


def _vector3(value: Any, context: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) != 3:
        raise ValueError(f"{context} must be a finite vector3")
    return tuple(_number(component, context) for component in value)  # type: ignore[return-value]


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    return value


def _validate_id(value: str, context: str) -> None:
    if _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Unsafe {context}: {value!r}")


def _validate_patch_id(value: str) -> None:
    if _PATCH_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Unsafe boundary patch_id: {value!r}")


def _validate_response_bindings(
    plan: SolverFlowCasePlan,
    requested: Mapping[str, Any],
    generated: Mapping[str, Any],
) -> None:
    requested_ids = requested.get("response_ids")
    generated_responses = generated.get("responses")
    if (
        not isinstance(requested_ids, Sequence)
        or isinstance(requested_ids, (str, bytes, bytearray))
        or not isinstance(generated_responses, Sequence)
        or isinstance(generated_responses, (str, bytes, bytearray))
    ):
        raise ValueError("requested.response_ids and generated.responses must be sequences")
    normalized_requested = tuple(str(value) for value in requested_ids)
    normalized_generated: list[str] = []
    for index, raw in enumerate(generated_responses):
        item = _mapping(raw, f"generated.responses[{index}]")
        response_id = item.get("response_id")
        if not isinstance(response_id, str):
            raise ValueError(f"generated.responses[{index}].response_id must be a string")
        _validate_id(response_id, "generated response_id")
        normalized_generated.append(response_id)
    for response_id in normalized_requested:
        _validate_id(response_id, "requested response_id")
    if len(set(normalized_requested)) != len(normalized_requested):
        raise ValueError("Duplicate requested response_id")
    if len(set(normalized_generated)) != len(normalized_generated):
        raise ValueError("Duplicate generated response_id")
    if (
        normalized_requested != plan.supported_response_ids
        or tuple(normalized_generated) != plan.supported_response_ids
    ):
        raise ValueError(
            "requested, generated, and supported response IDs must match for a renderable plan"
        )


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Metadata values must be finite")
    return value


__all__ = [
    "OpenFOAMPhysicsArtifacts",
    "openfoam_retained_field_boundary_specs",
    "render_openfoam_physics_files",
]
