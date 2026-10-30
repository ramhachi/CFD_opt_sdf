"""Body-fitted base adjoint case for the Work F surface-FD campaign.

Renders the OpenFOAM v2512 ``adjointOptimisationFoam`` dictionaries on a copy
of the qualified V1 body-fitted case: two adjoint solvers (drag and downforce)
with the registered response directions, and the ``volumetricBSplines`` shape
parameterization with an axis-aligned control-point volume whose boundary
control points are confined so the far-field stays fixed. Structural checks
verify the rendered dictionaries; the adjoint run and the ``faceSensNormal``
export are separate slices. This module never runs a solver.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ADJOINT_SOLVER_NAMES: dict[str, str] = {
    "drag": "adjDrag",
    "downforce": "adjDownforce",
}

_FOAM_HEADER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2512                                 |
|   \\\\  /    A nd           | www.openfoam.com                                |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      {object_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""


@dataclass(frozen=True)
class AdjointPatchRoles:
    """The primal patch roles that select the registered adjoint boundary conditions."""

    inflow: tuple[str, ...]
    outflow: tuple[str, ...]
    symmetry: tuple[str, ...]
    walls: tuple[str, ...]
    design: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "inflow": list(self.inflow),
            "outflow": list(self.outflow),
            "symmetry": list(self.symmetry),
            "walls": list(self.walls),
            "design": self.design,
        }


@dataclass(frozen=True)
class AdjointObjective:
    """One registered response as an OpenFOAM force objective."""

    response: str
    solver_name: str
    direction: tuple[float, float, float]
    patches: tuple[str, ...]
    area_m2: float
    rho_inf: float
    u_inf: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "solver_name": self.solver_name,
            "direction": list(self.direction),
            "patches": list(self.patches),
            "area_m2": self.area_m2,
            "rho_inf": self.rho_inf,
            "u_inf": self.u_inf,
        }


def _fmt(value: float) -> str:
    text = f"{float(value):.10g}"
    return text if "." in text or "e" in text else text + "."


def build_optimisation_dict(
    *,
    objectives: tuple[AdjointObjective, ...],
    primal_iterations: int,
    primal_residual: float,
    adjoint_iterations: int,
    adjoint_residual: float,
) -> str:
    """The ``system/optimisationDict`` for a single-run shape sensitivity case."""

    adjoint_blocks = []
    for objective in objectives:
        direction = " ".join(_fmt(value) for value in objective.direction)
        patches = " ".join(objective.patches)
        adjoint_blocks.append(
            f"""            {objective.solver_name}
            {{
                active                 true;
                type                   incompressible;
                solver                 adjointSimple;
                objectives
                {{
                    type incompressible;
                    objectiveNames
                    {{
                        {objective.response}
                        {{
                            weight     1.;
                            type       force;
                            patches    ({patches});
                            direction  ({direction});
                            Aref       {_fmt(objective.area_m2)};
                            rhoInf     {_fmt(objective.rho_inf)};
                            UInf       {_fmt(objective.u_inf)};
                        }}
                    }}
                }}
                ATCModel
                {{
                    ATCModel          standard;
                    extraConvection   0;
                    nSmooth           0;
                    zeroATCPatchTypes (wall patch);
                    maskType          pointCells;
                }}
                solutionControls
                {{
                    nIters {adjoint_iterations};
                    residualControl
                    {{
                        "pa.*"       {primal_residual:.1e};
                        "Ua.*"       {primal_residual:.1e};
                    }}
                }}
            }}
"""
        )
    design_patches = " ".join(sorted({patch for objective in objectives for patch in objective.patches}))
    return (
        _FOAM_HEADER.format(object_name="optimisationDict")
        + f"""
optimisationManager singleRun;

primalSolvers
{{
    op1
    {{
        active                 true;
        type                   incompressible;
        solver                 simple;
        solutionControls
        {{
            nIters {primal_iterations};
            residualControl
            {{
                "p.*"       {primal_residual:.1e};
                "U.*"       {primal_residual:.1e};
            }}
        }}
    }}
}}

adjointManagers
{{
    adjManager1
    {{
        primalSolver             op1;
        adjointSolvers
        {{
{''.join(adjoint_blocks)}        }}
    }}
}}

optimisation
{{
    designVariables
    {{
        type            shape;
        shapeType       volumetricBSplines;
        sensitivityType surface;
        patches         ({design_patches});
        includeSurfaceArea true;
    }}
}}

// ************************************************************************* //
"""
    )


def build_dynamic_mesh_dict(
    *,
    box_min: tuple[float, float, float],
    box_max: tuple[float, float, float],
    n_cps: tuple[int, int, int],
    degree: tuple[int, int, int],
) -> str:
    """The ``constant/dynamicMeshDict`` for the B-spline volume morpher."""

    lower = " ".join(_fmt(value) for value in box_min)
    upper = " ".join(_fmt(value) for value in box_max)
    return (
        _FOAM_HEADER.format(object_name="dynamicMeshDict")
        + f"""
solver volumetricBSplinesMotionSolver;

volumetricBSplinesMotionSolverCoeffs
{{
    box
    {{
        type    cartesian;
        nCPsU   {int(n_cps[0])};
        nCPsV   {int(n_cps[1])};
        nCPsW   {int(n_cps[2])};
        degreeU {int(degree[0])};
        degreeV {int(degree[1])};
        degreeW {int(degree[2])};

        controlPointsDefinition axisAligned;
        lowerCpBounds ({lower});
        upperCpBounds ({upper});

        confineBoundaryControlPoints true;
    }}
}}


// ************************************************************************* //
"""
    )


def build_adjoint_fv_schemes(source_text: str, solver_names: tuple[str, ...]) -> str:
    """Add the suffixed adjoint convection entries to the copied fvSchemes."""

    marker = "divSchemes\n{"
    if marker not in source_text:
        raise ValueError("source fvSchemes has no divSchemes block")
    block_start = source_text.index(marker) + len(marker)
    block_end = source_text.index("}", block_start)
    block = source_text[block_start:block_end]
    # the adjoint momentum stress term is not listed explicitly; the registered
    # tutorials resolve it through the block default, which the primal case sets
    # to none
    block = block.replace("default none;", "default Gauss linear;")
    entries = "".join(
        f"    div(-phi,Ua{name}) bounded Gauss upwind;\n" for name in solver_names
    )
    return source_text[:block_start] + "\n" + entries + block + source_text[block_end:]


def build_adjoint_fv_solution(source_text: str) -> str:
    """Add the adjoint solver and relaxation entries to the copied fvSolution."""

    marker = "solvers\n{"
    if marker not in source_text:
        raise ValueError("source fvSolution has no solvers block")
    start = source_text.index(marker) + len(marker)
    entries = (
        "\n    \"(p|pa).*\"\n"
        "    {\n"
        "        solver           PCG;\n"
        "        preconditioner   DIC;\n"
        "        tolerance        1e-9;\n"
        "        relTol           0.01;\n"
        "    }\n"
        "    \"(U|Ua).*\"\n"
        "    {\n"
        "        solver           PBiCGStab;\n"
        "        preconditioner   DILU;\n"
        "        tolerance        1e-9;\n"
        "        relTol           0.1;\n"
        "    }\n"
        "    \"(m|ma).*\"\n"
        "    {\n"
        "        solver           PCG;\n"
        "        preconditioner   DIC;\n"
        "        tolerance        1e-9;\n"
        "        relTol           0.01;\n"
        "    }\n"
        "    \"(d|da).*\"\n"
        "    {\n"
        "        solver           PCG;\n"
        "        preconditioner   DIC;\n"
        "        tolerance        1e-9;\n"
        "        relTol           0.01;\n"
        "    }\n"
    )
    updated = source_text[:start] + entries + source_text[start:]
    updated, fields_count = re.subn(
        r"(fields\s*\{)([^}]*)\}",
        r'\1\2 "pa.*" 0.3; }',
        updated,
        count=1,
    )
    updated, equations_count = re.subn(
        r"(equations\s*\{)([^}]*)\}",
        r'\1\2 "Ua.*" 0.7; }',
        updated,
        count=1,
    )
    if fields_count != 1 or equations_count != 1:
        raise ValueError("source fvSolution lacks the relaxationFactors fields/equations blocks")
    return updated


def build_adjoint_ras_properties() -> str:
    """The laminar adjoint turbulence properties required by the adjoint solver."""

    return (
        _FOAM_HEADER.format(object_name="adjointRASProperties")
        + """
adjointRASModel   adjointLaminar;

adjointTurbulence on;

printCoeffs       off;


// ************************************************************************* //
"""
    )


def build_adjoint_field_files(roles: AdjointPatchRoles) -> dict[str, str]:
    """The ``0/pa`` and ``0/Ua`` fields with the registered patch BC mapping."""

    wall_patches = tuple(dict.fromkeys((*roles.walls, roles.design)))

    def block(patch: str, body: str) -> str:
        return f"    {patch}\n    {{\n{body}    }}\n"

    pa_body = ""
    ua_body = ""
    for patch in roles.inflow:
        pa_body += block(patch, "        type            zeroGradient;\n")
        ua_body += block(
            patch,
            "        type            adjointInletVelocity;\n"
            "        value           uniform ( 0 0 0 );\n",
        )
    for patch in roles.outflow:
        pa_body += block(
            patch,
            "        type            adjointFarFieldPressure;\n"
            "        value           uniform 0;\n",
        )
        ua_body += block(
            patch,
            "        type            adjointOutletVelocity;\n"
            "        inletValue      uniform ( 0 0 0 );\n"
            "        value           uniform ( 0 0 0 );\n",
        )
    for patch in roles.symmetry:
        pa_body += block(patch, "        type            symmetryPlane;\n")
        ua_body += block(patch, "        type            symmetryPlane;\n")
    for patch in wall_patches:
        pa_body += block(patch, "        type            zeroGradient;\n")
        ua_body += block(
            patch,
            "        type            adjointWallVelocity;\n"
            "        value           uniform ( 0 0 0 );\n",
        )
    pa = (
        _FOAM_HEADER.format(object_name="pa")
        + """
dimensions      [ 0 2 -2 0 0 0 0 ];

internalField   uniform 0;

boundaryField
{
"""
        + pa_body
        + """}

// ************************************************************************* //
"""
    )
    ua = (
        _FOAM_HEADER.format(object_name="Ua")
        + """
dimensions      [ 0 1 -1 0 0 0 0 ];

internalField   uniform ( 0 0 0 );

boundaryField
{
"""
        + ua_body
        + """}

// ************************************************************************* //
"""
    )
    return {"0/pa": pa, "0/Ua": ua}


def render_adjoint_case(
    *,
    source_case: Path,
    target_case: Path,
    objectives: tuple[AdjointObjective, ...],
    patch_roles: AdjointPatchRoles,
    box_min: tuple[float, float, float],
    box_max: tuple[float, float, float],
    n_cps: tuple[int, int, int],
    degree: tuple[int, int, int],
    primal_iterations: int,
    primal_residual: float,
    adjoint_iterations: int,
    adjoint_residual: float,
) -> dict[str, Any]:
    """Copy the qualified case and write the adjoint dictionaries; refuse overwrite."""

    if target_case.exists():
        raise FileExistsError(f"adjoint case already exists: {target_case}")
    if not (source_case / "case_metadata.json").is_file():
        raise FileNotFoundError(f"source case lacks case_metadata.json: {source_case}")
    shutil.copytree(source_case, target_case)
    optimisation = target_case / "system" / "optimisationDict"
    mesh_dict = target_case / "constant" / "dynamicMeshDict"
    optimisation.write_text(
        build_optimisation_dict(
            objectives=objectives,
            primal_iterations=primal_iterations,
            primal_residual=primal_residual,
            adjoint_iterations=adjoint_iterations,
            adjoint_residual=adjoint_residual,
        ),
        encoding="utf-8",
        newline="\n",
    )
    mesh_dict.write_text(
        build_dynamic_mesh_dict(box_min=box_min, box_max=box_max, n_cps=n_cps, degree=degree),
        encoding="utf-8",
        newline="\n",
    )
    fv_solution = target_case / "system" / "fvSolution"
    fv_solution.write_text(
        build_adjoint_fv_solution(fv_solution.read_text(encoding="utf-8")),
        encoding="utf-8",
        newline="\n",
    )
    fv_schemes = target_case / "system" / "fvSchemes"
    fv_schemes.write_text(
        build_adjoint_fv_schemes(
            fv_schemes.read_text(encoding="utf-8"),
            tuple(objective.solver_name for objective in objectives),
        ),
        encoding="utf-8",
        newline="\n",
    )
    field_paths: dict[str, str] = {}
    generated_fields = build_adjoint_field_files(patch_roles)
    generated_fields["constant/adjointRASProperties"] = build_adjoint_ras_properties()
    for relative, text in generated_fields.items():
        path = target_case / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        field_paths[relative] = str(path)
    return {
        "target_case": str(target_case),
        "optimisation_dict": str(optimisation),
        "dynamic_mesh_dict": str(mesh_dict),
        "adjoint_fields": field_paths,
        "patch_roles": patch_roles.to_dict(),
        "objectives": [objective.to_dict() for objective in objectives],
    }


def verify_adjoint_case(
    case_dir: Path,
    *,
    objectives: tuple[AdjointObjective, ...],
    patch_roles: AdjointPatchRoles,
) -> dict[str, Any]:
    """Structural checks on the rendered dictionaries and adjoint fields (no solver)."""

    optimisation = (case_dir / "system" / "optimisationDict").read_text(encoding="utf-8")
    mesh_dict = (case_dir / "constant" / "dynamicMeshDict").read_text(encoding="utf-8")
    pa = (case_dir / "0" / "pa").read_text(encoding="utf-8")
    ua = (case_dir / "0" / "Ua").read_text(encoding="utf-8")
    checks: dict[str, bool] = {
        "optimisation_manager_single_run": "optimisationManager singleRun;" in optimisation,
        "primal_solver_simple": re.search(r"solver\s+simple;", optimisation) is not None,
        "adjoint_solver_type": optimisation.count("solver                 adjointSimple;")
        == len(objectives),
        "shape_parameterization": (
            "shapeType       volumetricBSplines;" in optimisation
            and "sensitivityType surface;" in optimisation
            and "includeSurfaceArea true;" in optimisation
        ),
        "mesh_morpher": "solver volumetricBSplinesMotionSolver;" in mesh_dict,
        "control_points_axis_aligned": "controlPointsDefinition axisAligned;" in mesh_dict,
        "boundary_control_points_confined": "confineBoundaryControlPoints true;" in mesh_dict,
        "pa_inflow_zero_gradient": all(
            re.search(rf"{patch}\s*\{{[^}}]*zeroGradient;", pa) is not None
            for patch in patch_roles.inflow
        ),
        "pa_outflow_far_field": all(
            re.search(rf"{patch}\s*\{{[^}}]*adjointFarFieldPressure;", pa) is not None
            for patch in patch_roles.outflow
        ),
        "pa_walls_zero_gradient": all(
            re.search(rf"{patch}\s*\{{[^}}]*zeroGradient;", pa) is not None
            for patch in (*patch_roles.walls, patch_roles.design)
        ),
        "ua_inflow_adjoint_inlet": all(
            re.search(rf"{patch}\s*\{{[^}}]*adjointInletVelocity;", ua) is not None
            for patch in patch_roles.inflow
        ),
        "ua_outflow_adjoint_outlet": all(
            re.search(rf"{patch}\s*\{{[^}}]*adjointOutletVelocity;", ua) is not None
            for patch in patch_roles.outflow
        ),
        "ua_walls_adjoint_wall": all(
            re.search(rf"{patch}\s*\{{[^}}]*adjointWallVelocity;", ua) is not None
            for patch in (*patch_roles.walls, patch_roles.design)
        ),
        "adjoint_fv_schemes": all(
            f"div(-phi,Ua{objective.solver_name})" in optimisation
            or f"div(-phi,Ua{objective.solver_name})"
            in (case_dir / "system" / "fvSchemes").read_text(encoding="utf-8")
            for objective in objectives
        ),
        "adjoint_fv_solution": (
            '"(U|Ua).*"' in (case_dir / "system" / "fvSolution").read_text(encoding="utf-8")
            and '"pa.*"' in (case_dir / "system" / "fvSolution").read_text(encoding="utf-8")
        ),
        "adjoint_ras_laminar": (
            "adjointRASModel   adjointLaminar;"
            in (case_dir / "constant" / "adjointRASProperties").read_text(encoding="utf-8")
        ),
        "symmetry_patches": all(
            re.search(rf"{patch}\s*\{{[^}}]*symmetryPlane;", pa) is not None
            and re.search(rf"{patch}\s*\{{[^}}]*symmetryPlane;", ua) is not None
            for patch in patch_roles.symmetry
        ),
    }
    for objective in objectives:
        direction = " ".join(_fmt(value) for value in objective.direction)
        checks[f"{objective.response}_solver_block"] = objective.solver_name in optimisation
        checks[f"{objective.response}_direction"] = f"direction  ({direction});" in optimisation
        checks[f"{objective.response}_patches"] = (
            f"patches    ({' '.join(objective.patches)});" in optimisation
        )
        checks[f"{objective.response}_reference"] = (
            f"Aref       {_fmt(objective.area_m2)};" in optimisation
            and f"UInf       {_fmt(objective.u_inf)};" in optimisation
        )
    return {
        "checks": checks,
        "pass": all(checks.values()),
        "failed_checks": sorted(key for key, value in checks.items() if not value),
    }


def verify_adjoint_case_with_openfoam(case_dir: Path, *, docker_image: str) -> dict[str, Any]:
    """Parse the rendered dictionaries with OpenFOAM's own dictionary reader."""

    name = "workf_adjoint_preflight_" + uuid.uuid4().hex
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--entrypoint",
        "bash",
        "--mount",
        f"type=bind,source={case_dir},target=/case",
        "-w",
        "/case",
        docker_image,
        "-lc",
        "foamDictionary system/optimisationDict -entry optimisationManager "
        "&& foamDictionary constant/dynamicMeshDict -entry solver",
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "pass": completed.returncode == 0,
    }


__all__ = [
    "ADJOINT_SOLVER_NAMES",
    "AdjointObjective",
    "AdjointPatchRoles",
    "build_adjoint_field_files",
    "build_adjoint_fv_schemes",
    "build_adjoint_fv_solution",
    "build_adjoint_ras_properties",
    "build_dynamic_mesh_dict",
    "build_optimisation_dict",
    "render_adjoint_case",
    "verify_adjoint_case",
    "verify_adjoint_case_with_openfoam",
]
