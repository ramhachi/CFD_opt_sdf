from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import load_project
from .design_state import read_density_design_state, resolve_design_state_path
from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE
from .openfoam import generate_openfoam_case
from .openfoam_sensitivity import export_openfoam_surface_sensitivity_to_csv
from .projection import project_surface_sensitivity_to_density
from .sdf import build_fields
from .sensitivity import write_mock_sensitivity_artifacts


ADJOINT_ADAPTER_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AdjointAdapterResult:
    design_state_json: Path
    backend_id: str
    solver_backend: str
    dry_run: bool
    primal_case_dir: Path
    adjoint_case_dir: Path
    command: list[str]
    returncode: int | None
    timed_out: bool
    error: str | None
    stdout_log: Path
    stderr_log: Path
    summary_path: Path
    sensitivity_vti: Path | None
    sensitivity_summary_json: Path | None
    surface_sensitivity_csv: Path | None
    surface_sensitivity_export: dict[str, object] | None
    raw_outputs: list[Path]
    conversion_mode: str
    force_patches: list[str]
    generated_files: list[str]
    preflight: dict[str, object]

    @property
    def ok(self) -> bool:
        return self.dry_run or (self.returncode == 0 and not self.timed_out and self.error is None)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "design_state_json",
            "primal_case_dir",
            "adjoint_case_dir",
            "stdout_log",
            "stderr_log",
            "summary_path",
            "sensitivity_vti",
            "sensitivity_summary_json",
            "surface_sensitivity_csv",
        ):
            if data[key] is not None:
                data[key] = str(data[key])
        data["raw_outputs"] = [str(path) for path in self.raw_outputs]
        data["ok"] = self.ok
        data["schema_version"] = ADJOINT_ADAPTER_SCHEMA_VERSION
        return data


def run_openfoam_adjoint_adapter(
    design_state_json: Path,
    *,
    primal_case_dir: Path | None = None,
    adjoint_case_dir: Path | None = None,
    solver_backend: str = "auto",
    dry_run: bool = True,
    timeout_seconds: int | None = None,
    mock_fallback: bool = True,
) -> AdjointAdapterResult:
    design_state_json = design_state_json.resolve()
    design_state = read_density_design_state(design_state_json)
    source_project = resolve_design_state_path(
        design_state_json,
        design_state.source_project,
        local_fallback=Path("project.yaml"),
    )
    config = load_project(source_project)
    primal_case_dir = primal_case_dir or (config.resolved_output_dir / "openfoam_front_wing")
    if not primal_case_dir.exists():
        bundle = build_fields(config)
        case_summary = generate_openfoam_case(config, bundle, primal_case_dir)
        (primal_case_dir / "openfoam_case_summary.json").write_text(
            json.dumps(case_summary.to_dict(), indent=2),
            encoding="utf-8",
        )

    adjoint_case_dir = adjoint_case_dir or (config.resolved_output_dir / "openfoam_adjoint_front_wing")
    _prepare_adjoint_case_skeleton(primal_case_dir, adjoint_case_dir)
    force_patches = _load_force_patches(primal_case_dir, config)
    generated_files = _write_adjoint_case_files(config, adjoint_case_dir, force_patches)
    preflight = _preflight_adjoint_case(adjoint_case_dir)
    (adjoint_case_dir / "adjoint_adapter_config.json").write_text(
        json.dumps(
            {
                "schema_version": ADJOINT_ADAPTER_SCHEMA_VERSION,
                "backend_id": "openfoam-adjoint",
                "source_design_state": str(design_state_json),
                "source_project": str(source_project),
                "primal_case_dir": str(primal_case_dir),
                "force_patches": force_patches,
                "generated_files": generated_files,
                "preflight": preflight,
                "note": "Initial adjointOptimisationFoam case files are generated. Raw sensitivity parsing is still incomplete.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    selected_backend = _select_adjoint_backend(solver_backend)
    command = _adjoint_command(selected_backend, adjoint_case_dir.resolve())
    stdout_log = adjoint_case_dir / "log.runAdjoint.stdout"
    stderr_log = adjoint_case_dir / "log.runAdjoint.stderr"
    summary_path = adjoint_case_dir / "adjoint_run_summary.json"
    returncode: int | None = None
    timed_out = False
    error = None
    if dry_run:
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
    elif not bool(preflight["executable_ready"]):
        error = "OpenFOAM adjoint case preflight failed: " + "; ".join(str(item) for item in preflight["blocking_issues"])
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text(error, encoding="utf-8")
    else:
        try:
            with stdout_log.open("w", encoding="utf-8") as stdout, stderr_log.open("w", encoding="utf-8") as stderr:
                completed = subprocess.run(
                    command,
                    cwd=adjoint_case_dir,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            returncode = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            error = f"OpenFOAM adjoint execution timed out after {exc.timeout} seconds"
            stderr_log.write_text(error, encoding="utf-8")
            if not stdout_log.exists():
                stdout_log.write_text("", encoding="utf-8")
        except OSError as exc:
            error = str(exc)
            stderr_log.write_text(error, encoding="utf-8")
            if not stdout_log.exists():
                stdout_log.write_text("", encoding="utf-8")

    execution_succeeded = dry_run or (returncode == 0 and not timed_out and error is None)
    raw_outputs = _collect_raw_sensitivity_outputs(adjoint_case_dir)
    sensitivity_vti = None
    sensitivity_summary_json = None
    normalized_surface_csv = None
    surface_sensitivity_export = None
    conversion_mode = "none"
    surface_csv = _select_surface_sensitivity_csv(raw_outputs)
    if surface_csv is not None:
        projected = project_surface_sensitivity_to_density(design_state_json, surface_csv, output_dir=adjoint_case_dir)
        sensitivity_vti = projected.sensitivity_vti
        sensitivity_summary_json = projected.sensitivity_summary_json
        normalized_surface_csv = surface_csv
        conversion_mode = "surface-csv-projection"
    elif (face_sensitivity := _select_openfoam_face_sensitivity(raw_outputs)) is not None:
        try:
            exported = export_openfoam_surface_sensitivity_to_csv(
                case_dir=adjoint_case_dir,
                sensitivity_file=face_sensitivity,
                output_csv=adjoint_case_dir / "surface_sensitivity.csv",
                patches=force_patches,
            )
            projected = project_surface_sensitivity_to_density(
                design_state_json,
                exported.output_csv,
                output_dir=adjoint_case_dir,
            )
            sensitivity_vti = projected.sensitivity_vti
            sensitivity_summary_json = projected.sensitivity_summary_json
            normalized_surface_csv = exported.output_csv
            surface_sensitivity_export = exported.to_dict()
            conversion_mode = "openfoam-faceSensNormal-projection"
        except Exception as exc:
            error = f"OpenFOAM sensitivity conversion failed: {exc}"
            conversion_mode = "openfoam-faceSensNormal-conversion-failed"
    elif raw_outputs:
        conversion_mode = "raw-output-detected-not-yet-parsed"
    elif dry_run and mock_fallback:
        artifacts = write_mock_sensitivity_artifacts(design_state_json, output_dir=adjoint_case_dir)
        sensitivity_vti = artifacts.sensitivity_vti
        sensitivity_summary_json = artifacts.sensitivity_summary_json
        conversion_mode = "mock-contract-fallback"
    elif not execution_succeeded:
        conversion_mode = "execution-failed-no-conversion"
    elif not dry_run:
        conversion_mode = "execute-no-raw-output"

    result = AdjointAdapterResult(
        design_state_json=design_state_json,
        backend_id="openfoam-adjoint",
        solver_backend=selected_backend,
        dry_run=dry_run,
        primal_case_dir=primal_case_dir,
        adjoint_case_dir=adjoint_case_dir,
        command=command,
        returncode=returncode,
        timed_out=timed_out,
        error=error,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        summary_path=summary_path,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=sensitivity_summary_json,
        surface_sensitivity_csv=normalized_surface_csv,
        surface_sensitivity_export=surface_sensitivity_export,
        raw_outputs=raw_outputs,
        conversion_mode=conversion_mode,
        force_patches=force_patches,
        generated_files=generated_files,
        preflight=preflight,
    )
    summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result


def _prepare_adjoint_case_skeleton(primal_case_dir: Path, adjoint_case_dir: Path) -> None:
    if adjoint_case_dir.exists():
        shutil.rmtree(adjoint_case_dir)
    ignore = shutil.ignore_patterns("postProcessing", "processor*", "log.*", "*.OpenFOAM")
    shutil.copytree(primal_case_dir, adjoint_case_dir, ignore=ignore)


def _load_force_patches(primal_case_dir: Path, config) -> list[str]:
    for relative in ("openfoam_case_summary.json", "case_metadata.json"):
        path = primal_case_dir / relative
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "force_patches" in data and isinstance(data["force_patches"], list):
            return [str(item) for item in data["force_patches"]]
        objective = data.get("objective")
        if isinstance(objective, dict) and isinstance(objective.get("force_patches"), list):
            return [str(item) for item in objective["force_patches"]]
    return [f"design_{_foam_name(ref.id)}" for ref in config.design_geometry]


def _write_adjoint_case_files(config, adjoint_case_dir: Path, force_patches: list[str]) -> list[str]:
    files: dict[str, str] = {
        "system/controlDict": _adjoint_control_dict(),
        "system/optimisationDict": _optimisation_dict(config, force_patches),
        "system/fvSchemes": _adjoint_fv_schemes(),
        "system/fvSolution": _adjoint_fv_solution(),
        "system/finite-area/faSchemes": _fa_schemes(),
        "system/finite-area/faSolution": _fa_solution(),
        "constant/adjointRASProperties": _adjoint_ras_properties(),
        "constant/turbulenceProperties": _spalart_allmaras_turbulence_properties(),
        "0/Ua": _adjoint_velocity_field(config),
        "0/pa": _adjoint_pressure_field(),
        "0/nuTilda": _nu_tilda_field(config),
        "0/nuaTilda": _nua_tilda_field(),
        "0/nut": _nut_spalart_allmaras_field(),
        "AllrunAdjoint": _allrun_adjoint(),
    }
    generated: list[str] = []
    for relative, text in files.items():
        path = adjoint_case_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        generated.append(relative)
    return generated


def _preflight_adjoint_case(adjoint_case_dir: Path) -> dict[str, object]:
    required_files = [
        "system/controlDict",
        "system/optimisationDict",
        "system/fvSchemes",
        "system/fvSolution",
        "system/finite-area/faSchemes",
        "system/finite-area/faSolution",
        "constant/adjointRASProperties",
        "constant/turbulenceProperties",
        "0/U",
        "0/p",
        "0/Ua",
        "0/pa",
        "0/nuTilda",
        "0/nuaTilda",
        "0/nut",
    ]
    missing = [relative for relative in required_files if not (adjoint_case_dir / relative).exists()]
    mesh_boundary = adjoint_case_dir / "constant" / "polyMesh" / "boundary"
    mesh_ready = mesh_boundary.exists()
    blocking = list(missing)
    if not mesh_ready:
        blocking.append("constant/polyMesh/boundary")
    return {
        "case_files_ready": not missing,
        "mesh_ready": mesh_ready,
        "executable_ready": not blocking,
        "missing_required_files": missing,
        "blocking_issues": blocking,
        "note": "Execute the primal mesh generation first, or pass an existing meshed primal_case_dir, before running adjointOptimisationFoam.",
    }


def _collect_raw_sensitivity_outputs(adjoint_case_dir: Path) -> list[Path]:
    patterns = [
        "**/*ensitivity*",
        "**/*Sensitivity*",
        "**/*sens*",
        "**/*Sens*",
        "**/faceSens*",
        "**/pointSens*",
        "**/smoothedSurfaceSens*",
        "**/grad*",
    ]
    outputs: list[Path] = []
    for pattern in patterns:
        outputs.extend(path for path in adjoint_case_dir.glob(pattern) if path.is_file())
    unique = sorted({path.resolve(): path for path in outputs}.values())
    return unique


def _select_surface_sensitivity_csv(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.suffix.lower() == ".csv" and "surface" in path.name.lower() and "sens" in path.name.lower():
            return path
    return None


def _select_openfoam_face_sensitivity(paths: list[Path]) -> Path | None:
    candidates = [
        path
        for path in paths
        if path.name.startswith("faceSensNormal")
        and not path.name.startswith("faceSensNormalVec")
        and path.suffix.lower() not in {".csv", ".vti"}
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: (0 if "RMult" in path.name or "Rmult" in path.name else 1, path.name))[0]


def _select_adjoint_backend(backend: str) -> str:
    normalized = backend.lower()
    if normalized not in {"auto", "local", "wsl", "docker"}:
        raise ValueError(f"Unsupported OpenFOAM adjoint backend: {backend}")
    if normalized != "auto":
        return normalized
    return "docker"


def _adjoint_command(backend: str, case_dir: Path) -> list[str]:
    image = os.environ.get("CFD_SDF_OPENFOAM_IMAGE", DEFAULT_OPENFOAM_DOCKER_IMAGE)
    if backend == "local":
        return ["bash", "-lc", f'adjointOptimisationFoam -case "{case_dir}"']
    if backend == "wsl":
        script = (
            'case_dir="$(wslpath -a "$1")" && '
            'adjointOptimisationFoam -case "$case_dir"'
        )
        return ["wsl", "bash", "-lc", script, "bash", str(case_dir)]
    if backend == "docker":
        return [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            "--mount",
            f"type=bind,source={case_dir},target=/case",
            "-w",
            "/case",
            image,
            "-lc",
            "adjointOptimisationFoam -case /case",
        ]
    raise ValueError(f"Unsupported OpenFOAM adjoint backend: {backend}")


def _optimisation_dict(config, force_patches: list[str]) -> str:
    patch_text = " ".join(force_patches) if force_patches else "design_.*"
    velocity = config.operating_point.velocity_mps
    density = config.operating_point.density
    return _foam_header("dictionary", "optimisationDict") + f"""
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
            consistent yes;
            nIters 200;
            residualControl
            {{
                "p.*"       1.e-5;
                "U.*"       1.e-5;
            }}
            averaging
            {{
                average     true;
                startIter   100;
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
            adjS1
            {{
                active                 true;
                type                   incompressible;
                solver                 adjointSimple;

                objectives
                {{
                    type incompressible;
                    objectiveNames
                    {{
                        negativeLift
                        {{
                            weight     1.;
                            type       force;
                            patches    ({patch_text});
                            direction  (0 0 1);
                            Aref       1;
                            rhoInf     {density:g};
                            UInf       {velocity:g};
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
                    consistent yes;
                    nIters 200;
                    residualControl
                    {{
                        "pa.*"       1.e-5;
                        "Ua.*"       1.e-5;
                    }}
                }}
            }}
        }}
    }}
}}

optimisation
{{
    designVariables
    {{
        sensitivityType multiple;
        sensitivityTypes
        (
            faceBased-RMult_2
        );
        patches          ({patch_text});

        faceBased-RMult_2
        {{
            sensitivityType       surface;
            patches               ({patch_text});
            includeSurfaceArea    true;
            writeAllSurfaceFiles  true;
            returnVectorField     false;
            smoothSensitivities   true;
            meanRadiusMultiplier  2;
            suffix                Rmult2;
            iters                 100;
        }}
    }}
}}
"""


def _adjoint_control_dict() -> str:
    return _foam_header("dictionary", "controlDict") + """
application     adjointOptimisationFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         400;
deltaT          1;
writeControl    timeStep;
writeInterval   200;
purgeWrite      1;
writeFormat     ascii;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
"""


def _adjoint_ras_properties() -> str:
    return _foam_header("dictionary", "adjointRASProperties") + """
adjointRASModel   adjointSpalartAllmaras;

adjointSpalartAllmarasCoeffs
{
    nSmooth           0;
    zeroATCPatchTypes (wall patch);
    maskType          pointCells;
}

adjointTurbulence on;
printCoeffs       off;
"""


def _spalart_allmaras_turbulence_properties() -> str:
    return _foam_header("dictionary", "turbulenceProperties") + """
simulationType RAS;

RAS
{
    RASModel        SpalartAllmaras;
    turbulence      on;
    printCoeffs     on;
}
"""


def _adjoint_fv_schemes() -> str:
    return _foam_header("dictionary", "fvSchemes") + """
ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;
    grad(nuTilda)   cellLimited Gauss linear 1;
    gradDConv       cellLimited Gauss linear 1;
    gradDaConv      cellLimited Gauss linear 1;
    gradUATC        cellLimited Gauss linear 1;
}

divSchemes
{
    default                 Gauss linear;
    div(phi,U)              bounded Gauss linearUpwindV grad(U);
    div(phi,nuTilda)        bounded Gauss upwind;
    div(yPhi,yWall)                 Gauss linearUpwind gradDConv;
    div(-phiMean,Ua)        bounded Gauss upwind;
    div(-phiMean,nuaTilda)  bounded Gauss upwind;
    div(-yPhi,da)                   Gauss upwind;
}

laplacianSchemes
{
    default         Gauss linear limited 0.333;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         limited 0.333;
}

wallDist
{
    method advectionDiffusion;
    advectionDiffusionCoeffs
    {
        method    meshWave;
        tolerance 1.e-5;
        maxIter   1000;
        epsilon   0.1;
    }
}
"""


def _adjoint_fv_solution() -> str:
    return _foam_header("dictionary", "fvSolution") + """
solvers
{
    "(p|pa)"
    {
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }

    ma
    {
        solver           PCG;
        preconditioner   DIC;
        tolerance        1e-9;
        relTol           0.01;
    };

    Phi
    {
        $p;
    }

    "(U|Ua|nuTilda|nuaTilda|yWall|da)"
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
        nSweeps         1;
    }
}

potentialFlow
{
    nNonOrthogonalCorrectors 10;
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent yes;
    pRefCell 0;
    pRefValue 0;
}

relaxationFactors
{
    fields
    {
        "p.*"    0.3;
        "pa.*"   0.7;
    }
    equations
    {
        U         0.7;
        Ua        0.3;
        nuTilda   0.7;
        nuaTilda  0.02;
        yWall     0.7;
        da        0.5;
    }
}

cache
{
    grad(U);
}
"""


def _fa_schemes() -> str:
    return _foam_header("dictionary", "faSchemes") + """
ddtSchemes
{
    default            steadyState;
}
gradSchemes
{
    default            Gauss linear;
}
divSchemes
{
    default            Gauss linear;
}
laplacianSchemes
{
    default            Gauss linear limited 0.333;
}
interpolationSchemes
{
    default            linear;
}
lnGradSchemes
{
    default            limited 0.333;
}
"""


def _fa_solution() -> str:
    return _foam_header("dictionary", "faSolution") + """
solvers
{
    smoothedSens
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-08;
        relTol          0.01;
    }
}

relaxationFactors
{
    smoothedSens    0.4;
}
"""


def _adjoint_velocity_field(config) -> str:
    return _foam_header("volVectorField", "Ua", "0") + """
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform (0 0 0);
boundaryField
{
    inlet { type adjointInletVelocity; value $internalField; }
    outlet { type adjointOutletVelocity; inletValue uniform (0 0 0); value $internalField; }
    sideMin { type symmetryPlane; }
    sideMax { type symmetryPlane; }
    top { type symmetryPlane; }
    bottom { type adjointWallVelocity; value $internalField; }
    ".*" { type adjointWallVelocity; value $internalField; }
}
"""


def _adjoint_pressure_field() -> str:
    return _foam_header("volScalarField", "pa", "0") + """
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    inlet { type zeroGradient; }
    outlet { type adjointFarFieldPressure; value $internalField; }
    sideMin { type symmetryPlane; }
    sideMax { type symmetryPlane; }
    top { type symmetryPlane; }
    bottom { type zeroGradient; }
    ".*" { type zeroGradient; }
}
"""


def _nu_tilda_field(config) -> str:
    nu = config.operating_point.viscosity / config.operating_point.density
    nu_tilda = 3.0 * nu
    return _foam_header("volScalarField", "nuTilda", "0") + f"""
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform {nu_tilda:.8g};
boundaryField
{{
    inlet {{ type fixedValue; value uniform {nu_tilda:.8g}; }}
    outlet {{ type inletOutlet; inletValue uniform {nu_tilda:.8g}; value uniform {nu_tilda:.8g}; }}
    sideMin {{ type symmetryPlane; }}
    sideMax {{ type symmetryPlane; }}
    top {{ type symmetryPlane; }}
    bottom {{ type fixedValue; value uniform 0; }}
    ".*" {{ type fixedValue; value uniform 0; }}
}}
"""


def _nua_tilda_field() -> str:
    return _foam_header("volScalarField", "nuaTilda", "0") + """
dimensions      [0 0 -1 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    inlet { type adjointInletNuaTilda; value uniform 0; }
    outlet { type adjointOutletNuaTilda; value uniform 0; }
    sideMin { type symmetryPlane; }
    sideMax { type symmetryPlane; }
    top { type symmetryPlane; }
    bottom { type fixedValue; value uniform 0; }
    ".*" { type fixedValue; value uniform 0; }
}
"""


def _nut_spalart_allmaras_field() -> str:
    return _foam_header("volScalarField", "nut", "0") + """
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    inlet { type calculated; value uniform 0; }
    outlet { type calculated; value uniform 0; }
    sideMin { type symmetryPlane; }
    sideMax { type symmetryPlane; }
    top { type symmetryPlane; }
    bottom { type nutUSpaldingWallFunction; value uniform 0; }
    ".*" { type nutUSpaldingWallFunction; value uniform 0; }
}
"""


def _allrun_adjoint() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

if [ ! -f constant/polyMesh/boundary ]; then
    echo "No mesh found in constant/polyMesh. Run the primal OpenFOAM mesh generation first."
    exit 2
fi

adjointOptimisationFoam -case .
"""


def _foam_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)


def _foam_header(class_name: str, object_name: str, location: str | None = None) -> str:
    location_line = f'    location    "{location}";\n' if location else ""
    return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       {class_name};
{location_line}    object      {object_name};
}}
"""
