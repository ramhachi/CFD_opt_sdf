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
        sensitivityType shapeFI;
        patches         ({design_patches});
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


def render_adjoint_case(
    *,
    source_case: Path,
    target_case: Path,
    objectives: tuple[AdjointObjective, ...],
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
    return {
        "target_case": str(target_case),
        "optimisation_dict": str(optimisation),
        "dynamic_mesh_dict": str(mesh_dict),
        "objectives": [objective.to_dict() for objective in objectives],
    }


def verify_adjoint_case(
    case_dir: Path, *, objectives: tuple[AdjointObjective, ...]
) -> dict[str, Any]:
    """Structural checks on the rendered dictionaries (no solver)."""

    optimisation = (case_dir / "system" / "optimisationDict").read_text(encoding="utf-8")
    mesh_dict = (case_dir / "constant" / "dynamicMeshDict").read_text(encoding="utf-8")
    checks: dict[str, bool] = {
        "optimisation_manager_single_run": "optimisationManager singleRun;" in optimisation,
        "primal_solver_simple": re.search(r"solver\s+simple;", optimisation) is not None,
        "adjoint_solver_type": optimisation.count("solver                 adjointSimple;")
        == len(objectives),
        "shape_parameterization": (
            "shapeType       volumetricBSplines;" in optimisation
            and "sensitivityType shapeFI;" in optimisation
        ),
        "mesh_morpher": "solver volumetricBSplinesMotionSolver;" in mesh_dict,
        "control_points_axis_aligned": "controlPointsDefinition axisAligned;" in mesh_dict,
        "boundary_control_points_confined": "confineBoundaryControlPoints true;" in mesh_dict,
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
    "build_dynamic_mesh_dict",
    "build_optimisation_dict",
    "render_adjoint_case",
    "verify_adjoint_case",
    "verify_adjoint_case_with_openfoam",
]
