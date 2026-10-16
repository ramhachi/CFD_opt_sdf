"""T2-0a (#57, EXPLORATORY_COMMITTED): OpenFOAM v2512 dictionary text for the 2D ground-effect wing cases.

Pure text generation, no solver or gmsh dependency. Everything below is untested against OpenFOAM (v2512 syntax written from
memory of the ESI tutorials); the smoke stage of the t20a kernel is the first execution.
"""
from __future__ import annotations

import math
import re

HEAD = "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class %s;\n    object %s;\n}\n\n"
DIM = {"U": "[0 1 -1 0 0 0 0]", "p": "[0 2 -2 0 0 0 0]", "nut": "[0 2 -1 0 0 0 0]", "nuTilda": "[0 2 -1 0 0 0 0]",
       "k": "[0 2 -2 0 0 0 0]", "omega": "[0 0 -1 0 0 0 0]", "ReThetat": "[0 0 0 0 0 0 0]", "gammaInt": "[0 0 0 0 0 0 0]"}
WALLS = ("airfoil", "ground")
LM_RELAX = {"U": 0.5, "p": 0.2, "turb": 0.3}   # kOmegaSSTLM continuation stage (SIMPLE, not SIMPLEC): lead's values for the transition equations and the segregated coupling


def retheta_t(tu_pct: float) -> float:
    """Langtry-Menter free-stream Re_theta_t correlation (zero pressure gradient), valid for Tu <= 1.3 %."""
    assert tu_pct <= 1.3
    return 1173.51 - 589.428 * tu_pct + 0.2196 / tu_pct ** 2


def field(name: str, cls: str, internal: str, patches: dict) -> str:
    body = "".join(f"    {p}\n    {{\n        " + "\n        ".join(v) + "\n    }\n" for p, v in patches.items())
    return (HEAD % (cls, name)) + f"dimensions {DIM[name]};\n\ninternalField {internal};\n\nboundaryField\n{{\n{body}}}\n"


def fixed(v):
    return [f"type fixedValue;", f"value uniform {v};"]


ZG = ["type zeroGradient;"]
SLIP = ["type slip;"]
CALC = ["type calculated;", "value uniform 0;"]


def fields(model: dict, u: float, nu: float, tu: float, length: float) -> dict[str, str]:
    """0/ field files. `model` is a t20_case.MODELS entry; inlet turbulence from Tu and an integral length scale."""
    k = 1.5 * (tu * u) ** 2
    omega = math.sqrt(k) / (0.09 ** 0.25 * length)
    lowre = model["wall"] == "wr"
    out = {
        "U": field("U", "volVectorField", f"uniform ({u} 0 0)",
                   {"inlet": fixed(f"({u} 0 0)"), "outlet": ZG, "top": SLIP, "ground": fixed(f"({u} 0 0)"),
                    "airfoil": ["type noSlip;"], "front": ["type empty;"], "back": ["type empty;"]}),
        "p": field("p", "volScalarField", "uniform 0",
                   {"inlet": ZG, "outlet": fixed("0"), "top": ZG, "ground": ZG, "airfoil": ZG,
                    "front": ["type empty;"], "back": ["type empty;"]}),
    }

    def turb(name, inlet, wall_wf, wall_lr, internal):
        w = wall_lr if lowre else wall_wf
        return field(name, "volScalarField", internal,
                     {"inlet": fixed(inlet), "outlet": ["type inletOutlet;", f"inletValue uniform {inlet};", f"value uniform {inlet};"],
                      "top": ZG, "ground": w, "airfoil": w, "front": ["type empty;"], "back": ["type empty;"]})

    nut_wall = ["type nutLowReWallFunction;", "value uniform 0;"] if lowre else None
    base = {"inlet": CALC, "outlet": CALC, "top": CALC, "front": ["type empty;"], "back": ["type empty;"]}

    def nut(wall_bc):
        return field("nut", "volScalarField", "uniform 0", {**base, "ground": wall_bc, "airfoil": wall_bc})

    if model["foam"] == "SpalartAllmaras":
        nt = 5 * nu
        out["nuTilda"] = turb("nuTilda", nt, fixed("0"), fixed("0"), f"uniform {nt}")
        out["nut"] = nut(["type nutUSpaldingWallFunction;", "value uniform 0;"])
    else:
        out["k"] = turb("k", k, ["type kqRWallFunction;", f"value uniform {k};"], fixed("1e-12"), f"uniform {k}")
        out["omega"] = turb("omega", omega, ["type omegaWallFunction;", f"value uniform {omega};"],
                            ["type omegaWallFunction;", f"value uniform {omega};"], f"uniform {omega}")
        out["nut"] = nut(nut_wall or ["type nutkWallFunction;", "value uniform 0;"])
        if model["foam"] == "kOmegaSSTLM":
            re_t = retheta_t(100 * tu)
            out["ReThetat"] = turb("ReThetat", re_t, ZG, ZG, f"uniform {re_t}")
            out["gammaInt"] = turb("gammaInt", 1, ZG, ZG, "uniform 1")
    return out


def system_and_constant(model: dict, mesh: dict, p: dict) -> dict[str, str]:
    """system/* and constant/* text. p: u, nu, chord, z (extrusion thickness), iters (endTime); optional start (`startTime` default, `latestTime` for a continuation).
    model["stage2"] = True writes the transition continuation: SIMPLE (consistent no) with the low relaxation factors of LM_RELAX, to be run from the latest time of
    the kOmegaSST stage (the runner copies the 0/ gammaInt and ReThetat there and swaps these files in)."""
    scal = ["nuTilda"] if model["foam"] == "SpalartAllmaras" else ["k", "omega"] + (["ReThetat", "gammaInt"] if model["foam"] == "kOmegaSSTLM" else [])
    relax = '"(' + "|".join(["U"] + scal) + ')"'
    rtol = "".join(f"        {s} 1e-6;\n" for s in scal)
    stage2 = model.get("stage2", False)
    if stage2:
        relax_block = ("    fields {{ p {p}; }}\n    equations\n    {{\n        U {U};\n        \"({t})\" {T};\n    }}\n"
                       .format(p=LM_RELAX["p"], U=LM_RELAX["U"], t="|".join(scal), T=LM_RELAX["turb"]))
    else:
        relax_block = f"    equations {{ {relax} {model['relax']}; }}\n"
    turb = ("simulationType RAS;\n\nRAS\n{\n    model " + model["foam"] + ";\n    turbulence on;\n    printCoeffs on;\n}\n")
    div_t = "".join(f"    div(phi,{s}) bounded Gauss upwind;\n" for s in ("nuTilda", "k", "omega", "ReThetat", "gammaInt"))
    force_common = (f"        libs (forces);\n        patches (airfoil);\n        rho rhoInf;\n        rhoInf 1;\n        CofR ({0.25 * p['chord']:.6g} 0 0);\n"
                    f"        writeControl timeStep;\n        writeInterval 1;\n")
    return {
        "system/controlDict": (HEAD % ("dictionary", "controlDict")) + f"""application simpleFoam;
startFrom {p.get('start', 'startTime')};
startTime 0;
stopAt endTime;
endTime {p['iters']};
deltaT 1;
writeControl timeStep;
writeInterval {p['iters']};
purgeWrite 1;
writeFormat ascii;
writePrecision 8;
runTimeModifiable false;

functions
{{
    forceCoeffs
    {{
        type forceCoeffs;
{force_common}        dragDir (1 0 0);
        liftDir (0 -1 0);
        pitchAxis (0 0 1);
        magUInf {p['u']};
        lRef {p['chord']};
        Aref {p['chord'] * p['z']:.10g};
    }}
    forces
    {{
        type forces;
{force_common}    }}
}}
""",
        "system/fvSchemes": (HEAD % ("dictionary", "fvSchemes")) + f"""ddtSchemes {{ default steadyState; }}
gradSchemes {{ default Gauss linear; grad(U) cellLimited Gauss linear 1; }}
divSchemes
{{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
{div_t}    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}
laplacianSchemes {{ default Gauss linear corrected; }}
interpolationSchemes {{ default linear; }}
snGradSchemes {{ default corrected; }}
wallDist {{ method meshWave; }}
""",
        "system/fvSolution": (HEAD % ("dictionary", "fvSolution")) + f"""solvers
{{
    p {{ solver GAMG; smoother GaussSeidel; tolerance 1e-9; relTol 0.1; }}
    "(U|k|omega|nuTilda|ReThetat|gammaInt)" {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-10; relTol 0.1; }}
}}
SIMPLE
{{
    nNonOrthogonalCorrectors 1;
    consistent {'no' if stage2 else 'yes'};
    residualControl
    {{
        p 1e-6;
        U 1e-7;
{rtol}    }}
}}
relaxationFactors
{{
{relax_block}}}
""",
        "constant/transportProperties": (HEAD % ("dictionary", "transportProperties")) + f"transportModel Newtonian;\nnu [0 2 -1 0 0 0 0] {p['nu']};\n",
        "constant/momentumTransport": (HEAD % ("dictionary", "momentumTransport")) + turb,
        "constant/turbulenceProperties": (HEAD % ("dictionary", "turbulenceProperties")) + turb,
    }


def fv_options(u_max: float) -> str:
    """OPTIONAL velocity limiter for the LM stage. UNCERTAIN: ESI v2512's `velocityDampingConstraint` (UMax, C) written from memory of the fvOptions constraints;
    never executed. The runner removes system/fvOptions and reruns the stage once if the stage dies before its first iteration (see runner.run_lm_stage)."""
    return (HEAD % ("dictionary", "fvOptions")) + f"limitU\n{{\n    type velocityDampingConstraint;\n    active yes;\n    selectionMode all;\n    UMax {u_max};\n    C 1;\n}}\n"


def fix_boundary(text: str) -> str:
    """gmshToFoam writes every patch as `type patch`: make front/back `empty` and airfoil/ground `wall` (wall functions need wall patches)."""
    for name, typ in (("front", "empty"), ("back", "empty"), ("airfoil", "wall"), ("ground", "wall")):
        text, n = re.subn(rf"(\b{name}\s*\{{[^{{}}]*?)type\s+\w+\s*;", rf"\g<1>type {typ};", text, count=1)
        if n != 1:
            raise ValueError(f"patch {name!r} not found in the boundary file")
    return text
