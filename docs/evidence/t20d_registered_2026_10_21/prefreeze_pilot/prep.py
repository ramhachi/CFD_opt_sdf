# force-free timing pilot: strip function objects from the steady controlDict; write PIMPLE dictionaries for stage 2
import re, sys
from pathlib import Path
case = Path(sys.argv[1]); maxco = sys.argv[2]; nouter = sys.argv[3]
cd = case / "system/controlDict"
t = cd.read_text()
t = t[:t.index("functions")]  # no forces
cd.write_text(t)
H = "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n    object %s;\n}\n\n"
p2 = case / "pimple"; p2.mkdir(exist_ok=True)
(p2 / "controlDict").write_text(H % "controlDict" + f"""application pimpleFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime 0.0075;
deltaT 1e-6;
writeControl adjustable;
writeInterval 1;
purgeWrite 1;
writeFormat ascii;
writePrecision 8;
runTimeModifiable false;
adjustTimeStep yes;
maxCo {maxco};
maxDeltaT 1e-4;
""")
(p2 / "fvSchemes").write_text(H % "fvSchemes" + """ddtSchemes { default backward; }
gradSchemes { default Gauss linear; grad(U) cellLimited Gauss linear 1; }
divSchemes
{
    default none;
    div(phi,U) Gauss linearUpwind grad(U);
    div(phi,nuTilda) Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
""")
(p2 / "fvSolution").write_text(H % "fvSolution" + f"""solvers
{{
    p {{ solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0.01; }}
    pFinal {{ solver GAMG; smoother GaussSeidel; tolerance 1e-7; relTol 0; }}
    "(U|nuTilda)" {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }}
    "(U|nuTilda)Final" {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0; }}
}}
PIMPLE
{{
    momentumPredictor yes;
    nOuterCorrectors {nouter};
    nCorrectors 2;
    nNonOrthogonalCorrectors 1;
}}
relaxationFactors {{ equations {{ ".*" 1; }} }}
""")
