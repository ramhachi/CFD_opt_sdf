"""T2-0b (#57, REGISTERED): adjointOptimisationFoam (v2512) feasibility case for the 2D ground-effect wing, and the rigid-rotation projection.

Dictionaries follow the Stage S Work F adjoint case that ran on v2512 (`src/cfd_sdf/stage_s_adjoint_case.py`, singleRun, adjointSimple, objective
`force`, volumetricBSplines, `sensitivityType surface`, adjointLaminar = frozen turbulence) with this case's patches. Not run locally (no OpenFOAM);
UNVERIFIED for this case: the slip adjoint BC on the top patch, the 2D (one-cell, empty front/back) use of the box. No control point is confined,
so every point with support on the section is a design variable (required by the projection below); z components are reported and ignored (V_z = 0).
Projection: derivative rows are joined to control points by varID = 3 * cp + component (cp = i + nU (j + nV k), the CSV row order; checked on the
Stage S files). A rigid motion of all control points moves every point inside the box rigidly (the clamped B-spline basis is a partition of unity), so
dJ/dalpha = sum over active (cp, c) of total[3 cp + c] * V_c(cp) with V = (-(y - y_LE), x - x_low) per radian: rotation about the LE plus the vertical shift
that keeps the lowest suction-side point at h (what `t20_case.airfoil_points(h, delta_alpha)` does). Pure text and numpy, no solver.
"""
from __future__ import annotations

import csv
import re
import io
import math

import numpy as np

SOLVER = "adjDownforce"
HEAD = "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class %s;\n    object %s;\n}\n\n"
BOX_NCPS, BOX_DEGREE = (10, 6, 3), (3, 3, 2)


def box_bounds(h: float, chord: float, z: float) -> tuple[tuple, tuple]:
    """Control-point box around the section at ride height h: x in [-0.15 c, 1.15 c], y in [h/2, h + 0.4 c], z one cell plus margins."""
    return (-0.15 * chord, 0.5 * h, -0.5 * z), (1.15 * chord, h + 0.4 * chord, 1.5 * z)


def optimisation_dict(u: float, aref: float, primal_iters: int, adjoint_iters: int) -> str:
    return (HEAD % ("dictionary", "optimisationDict")) + f"""optimisationManager singleRun;

primalSolvers
{{
    op1
    {{
        active true;
        type incompressible;
        solver simple;
        solutionControls
        {{
            nIters {primal_iters};
            residualControl {{ "p.*" 1e-7; "U.*" 1e-7; }}
        }}
    }}
}}

adjointManagers
{{
    adjManager1
    {{
        primalSolver op1;
        adjointSolvers
        {{
            {SOLVER}
            {{
                active true;
                type incompressible;
                solver adjointSimple;
                objectives
                {{
                    type incompressible;
                    objectiveNames
                    {{
                        downforce
                        {{
                            weight 1.;
                            type force;
                            patches (airfoil);
                            direction (0 -1 0);
                            Aref {aref:.10g};
                            rhoInf 1.;
                            UInf {u:.10g};
                        }}
                    }}
                }}
                ATCModel
                {{
                    ATCModel standard;
                    extraConvection 0;
                    nSmooth 0;
                    zeroATCPatchTypes (wall patch);
                    maskType pointCells;
                }}
                solutionControls
                {{
                    nIters {adjoint_iters};
                    residualControl {{ "pa.*" 1e-7; "Ua.*" 1e-7; }}
                }}
            }}
        }}
    }}
}}

optimisation
{{
    designVariables
    {{
        type shape;
        shapeType volumetricBSplines;
        sensitivityType surface;
        patches (airfoil);
        includeSurfaceArea true;
    }}
}}
"""


def dynamic_mesh_dict(lo: tuple, hi: tuple) -> str:
    f = lambda v: " ".join(f"{x:.10g}" for x in v)
    (nu, nv, nw), (du, dv, dw) = BOX_NCPS, BOX_DEGREE
    return (HEAD % ("dictionary", "dynamicMeshDict")) + f"""solver volumetricBSplinesMotionSolver;

volumetricBSplinesMotionSolverCoeffs
{{
    box
    {{
        type cartesian;
        nCPsU {nu};
        nCPsV {nv};
        nCPsW {nw};
        degreeU {du};
        degreeV {dv};
        degreeW {dw};
        controlPointsDefinition axisAligned;
        lowerCpBounds ({f(lo)});
        upperCpBounds ({f(hi)});
        confineBoundaryControlPoints false;
    }}
}}
"""


def adjoint_fields() -> dict[str, str]:
    def fld(name, cls, dim, internal, patches):
        body = "".join(f"    {p}\n    {{\n" + "".join(f"        {l}\n" for l in v) + "    }\n" for p, v in patches.items())
        return (HEAD % (cls, name)) + f"dimensions {dim};\n\ninternalField {internal};\n\nboundaryField\n{{\n{body}}}\n"
    zero = "uniform (0 0 0)"
    wall = ["type adjointWallVelocity;", f"value {zero};"]
    empty = ["type empty;"]
    ua = fld("Ua", "volVectorField", "[0 1 -1 0 0 0 0]", zero, {
        "inlet": ["type adjointInletVelocity;", f"value {zero};"],
        "outlet": ["type adjointOutletVelocity;", f"inletValue {zero};", f"value {zero};"],
        "top": ["type slip;"], "ground": wall, "airfoil": wall, "front": empty, "back": empty})
    pa = fld("pa", "volScalarField", "[0 2 -2 0 0 0 0]", "uniform 0", {
        "inlet": ["type zeroGradient;"], "outlet": ["type adjointFarFieldPressure;", "value uniform 0;"],
        "top": ["type zeroGradient;"], "ground": ["type zeroGradient;"], "airfoil": ["type zeroGradient;"], "front": empty, "back": empty})
    ras = (HEAD % ("dictionary", "adjointRASProperties")) + "adjointRASModel adjointLaminar;\n\nadjointTurbulence on;\n\nprintCoeffs off;\n"
    return {"0/Ua": ua, "0/pa": pa, "constant/adjointRASProperties": ras}


def fv_schemes(primal: str) -> str:
    """Primal fvSchemes with the div block default opened to `Gauss linear` (adjoint stress terms, as Stage S) and the adjoint convection added."""
    out = primal.replace("    default none;\n", f"    default Gauss linear;\n    div(-phi,Ua{SOLVER}) bounded Gauss upwind;\n", 1)
    assert out != primal, "primal fvSchemes lacks `default none;` in divSchemes"
    return out


def fv_solution(primal: str) -> str:
    """Primal fvSolution plus the adjoint solver entries and relaxation (Stage S values)."""
    extra = ('    "(pa).*" { solver GAMG; smoother GaussSeidel; tolerance 1e-9; relTol 0.1; }\n'
             '    "(Ua).*" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-10; relTol 0.1; }\n'
             '    "(m|ma|d|da).*" { solver PCG; preconditioner DIC; tolerance 1e-9; relTol 0.01; }\n')
    out = primal.replace("solvers\n{\n", "solvers\n{\n" + extra, 1)
    out = out.replace("relaxationFactors\n{\n", 'relaxationFactors\n{\n    fields { "pa.*" 0.3; }\n', 1)
    out = out.replace("    equations { ", '    equations { "Ua.*" 0.7; ', 1)
    assert out.count('"Ua.*" 0.7') == 1 and out.count('"pa.*" 0.3') == 1 and '"(pa).*"' in out, "primal fvSolution layout differs from t20_foam"
    return out


def control_dict(primal: str) -> str:
    """Primal controlDict with adjointOptimisationFoam, start from 0 (the converged primal fields are copied there), a large endTime (each primal and adjoint
    iteration advances Time, as in the Stage S run) and the final write left to the solver."""
    out = primal
    for key, val in (("application", "adjointOptimisationFoam"), ("startFrom", "startTime"), ("endTime", "100000"), ("writeInterval", "100000"), ("purgeWrite", "0")):
        new, n = re.subn(rf"^{key} .*;$", f"{key} {val};", out, count=1, flags=re.M)
        assert n == 1, f"controlDict lacks {key}"
        out = new
    return out


def projected_derivatives(derivative_text: str, control_points_csv: str, x_low: float, y_le: float) -> dict:
    """Projections of a volumetricBSplines derivative file ('#varID total ...') onto rigid fields of all box control points (CSV row order):
    rotation V = (-(y - y_LE), x - x_low) per degree (LE toward the ground = +, ride height held), x- and y-translation per mm."""
    rows = list(csv.reader(io.StringIO(control_points_csv)))
    cps = np.array([[float(v) for v in r[:3]] for r in rows[1:] if r])
    total = {}
    for line in derivative_text.splitlines():
        parts = line.split()
        if parts and not parts[0].startswith("#"):
            total[int(parts[0])] = float(parts[1])
    if not total or not all(math.isfinite(v) for v in total.values()):
        raise ValueError("empty or non-finite derivative file")
    if max(total) >= 3 * len(cps) or min(total) < 0:
        raise ValueError("varID outside the control-point range")
    n = len(cps)

    def project(vel):
        return float(sum(t * vel[v // 3, v % 3] for v, t in total.items()))
    rot = np.c_[-(cps[:, 1] - y_le), cps[:, 0] - x_low, np.zeros(n)]
    return {"rotation_per_deg": project(rot) * math.pi / 180,
            "x_translation_per_mm": project(np.tile([1e-3, 0, 0], (n, 1))), "y_translation_per_mm": project(np.tile([0, 1e-3, 0], (n, 1))),
            "n_vars": len(total), "n_cps": n, "varids_complete": set(v for v in total if v % 3 < 2) == set(range(3 * n)) - set(range(2, 3 * n, 3)),
            "z_vars_nonzero": sum(1 for v, t in total.items() if v % 3 == 2 and t != 0)}
