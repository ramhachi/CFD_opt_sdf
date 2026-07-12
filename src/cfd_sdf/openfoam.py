from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .config import MeshRef, ProjectConfig, RootSpec
from .sdf import FieldBundle


@dataclass(frozen=True)
class OpenFoamCaseSummary:
    case_dir: Path
    stl_count: int
    force_patches: list[str]
    generated_files: list[str]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["case_dir"] = str(self.case_dir)
        return data


def generate_openfoam_case(config: ProjectConfig, bundle: FieldBundle, case_dir: Path) -> OpenFoamCaseSummary:
    case_dir.mkdir(parents=True, exist_ok=True)
    for relative in ("0", "constant", "constant/triSurface", "system", "postProcessing"):
        (case_dir / relative).mkdir(parents=True, exist_ok=True)

    copied = _copy_stls(config, case_dir / "constant" / "triSurface")
    force_patches = [f"design_{_patch_name(ref.id)}" for ref in config.design_geometry]
    metadata = _metadata(config, bundle, copied, force_patches)

    files: dict[str, str] = {
        "system/blockMeshDict": _block_mesh_dict(bundle),
        "system/surfaceFeatureExtractDict": _surface_feature_extract_dict(copied),
        "system/snappyHexMeshDict": _snappy_hex_mesh_dict(config, bundle, copied),
        "system/controlDict": _control_dict(config, force_patches),
        "system/fvSchemes": _fv_schemes(),
        "system/fvSolution": _fv_solution(),
        "system/decomposeParDict": _decompose_par_dict(),
        "constant/transportProperties": _transport_properties(config),
        "constant/turbulenceProperties": _turbulence_properties(),
        "0/U": _field_u(config),
        "0/p": _scalar_field("p", "0"),
        "0/k": _scalar_field("k", "1e-4"),
        "0/omega": _scalar_field("omega", "10"),
        "0/nut": _scalar_field("nut", "0"),
        "Allrun": _allrun(),
        "Allclean": _allclean(),
        "Allrun.ps1": _allrun_ps1(),
        "postprocess_forces.py": _postprocess_forces_py(),
        "case_metadata.json": json.dumps(metadata, indent=2),
    }

    generated = []
    for relative, text in files.items():
        path = case_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        generated.append(relative)

    return OpenFoamCaseSummary(
        case_dir=case_dir,
        stl_count=len(copied),
        force_patches=force_patches,
        generated_files=generated,
    )


def _copy_stls(config: ProjectConfig, tri_surface_dir: Path) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []

    def copy_refs(role: str, refs: list[MeshRef]) -> None:
        for ref in refs:
            src = config.resolve(ref.file)
            name = f"{role}_{_patch_name(ref.id)}.stl"
            shutil.copyfile(src, tri_surface_dir / name)
            copied.append({"role": role, "id": ref.id, "file": name, "patch": _patch_name(ref.id)})

    copy_refs("fixed", config.fixed_solids)
    copy_refs("design", config.design_geometry)
    copy_refs("allowed", config.design_domains)
    copy_refs("forbidden", config.forbidden_regions)
    for root in config.roots:
        if root.type == "stl" and root.file is not None:
            src = config.resolve(root.file)
            name = f"root_{_patch_name(root.id)}.stl"
            shutil.copyfile(src, tri_surface_dir / name)
            copied.append({"role": "root", "id": root.id, "file": name, "patch": _patch_name(root.id)})
    return copied


def _metadata(
    config: ProjectConfig,
    bundle: FieldBundle,
    copied: list[dict[str, str]],
    force_patches: list[str],
) -> dict[str, object]:
    return {
        "source_project": str(config.path),
        "grid": {
            "origin": bundle.grid.origin.tolist(),
            "spacing": bundle.grid.spacing,
            "shape": bundle.grid.shape,
            "bounds": bundle.grid.bounds.tolist(),
        },
        "component_labels": bundle.component_labels,
        "tri_surface_files": copied,
        "roots": [_root_metadata(root) for root in config.roots],
        "constraints": {
            "min_thickness_mm": config.constraints.min_thickness_mm,
            "rule_margin_mm": config.constraints.rule_margin_mm,
            "require_eroded_connectivity": config.constraints.require_eroded_connectivity,
        },
        "objective": {
            "type": config.objective.type,
            "efficiency_min": config.objective.efficiency_min,
            "force_patches": force_patches,
        },
        "operating_point": {
            "velocity_mps": config.operating_point.velocity_mps,
            "density": config.operating_point.density,
            "viscosity": config.operating_point.viscosity,
        },
    }


def _root_metadata(root: RootSpec) -> dict[str, object]:
    return {
        "id": root.id,
        "type": root.type,
        "file": str(root.file) if root.file else None,
        "center_m": root.center_m,
        "radius_m": root.radius_m,
        "extents_m": root.extents_m,
    }


def _block_mesh_dict(bundle: FieldBundle) -> str:
    bounds = bundle.grid.bounds
    lo = bounds[0]
    hi = bounds[1]
    lengths = hi - lo
    cells = np.maximum(np.ceil(lengths / (4.0 * bundle.grid.spacing)).astype(int), 1)
    vertices = [
        (lo[0], lo[1], lo[2]),
        (hi[0], lo[1], lo[2]),
        (hi[0], hi[1], lo[2]),
        (lo[0], hi[1], lo[2]),
        (lo[0], lo[1], hi[2]),
        (hi[0], lo[1], hi[2]),
        (hi[0], hi[1], hi[2]),
        (lo[0], hi[1], hi[2]),
    ]
    vertex_text = "\n".join(f"    ({x:g} {y:g} {z:g})" for x, y, z in vertices)
    return _foam_header("dictionary", "blockMeshDict") + f"""
scale 1;

vertices
(
{vertex_text}
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({cells[0]} {cells[1]} {cells[2]}) simpleGrading (1 1 1)
);

edges ();

boundary
(
    inlet {{ type patch; faces ((0 4 7 3)); }}
    outlet {{ type patch; faces ((1 2 6 5)); }}
    sideMin {{ type symmetryPlane; faces ((0 1 5 4)); }}
    sideMax {{ type symmetryPlane; faces ((3 7 6 2)); }}
    top {{ type symmetryPlane; faces ((4 5 6 7)); }}
    bottom {{ type wall; faces ((0 3 2 1)); }}
);

mergePatchPairs ();
"""


def _surface_feature_extract_dict(copied: list[dict[str, str]]) -> str:
    entries = []
    for item in copied:
        if item["role"] in {"fixed", "design"}:
            entries.append(
                f"""
{item["file"]}
{{
    extractionMethod    extractFromSurface;
    extractFromSurfaceCoeffs
    {{
        includedAngle   150;
    }}
    writeObj            yes;
}}
"""
            )
    return _foam_header("dictionary", "surfaceFeatureExtractDict") + "\n".join(entries)


def _snappy_hex_mesh_dict(
    config: ProjectConfig,
    bundle: FieldBundle,
    copied: list[dict[str, str]],
) -> str:
    bounds = bundle.grid.bounds
    lo = bounds[0]
    hi = bounds[1]
    lengths = hi - lo
    location = np.array(
        [
            lo[0] + 0.10 * lengths[0],
            0.5 * (lo[1] + hi[1]),
            lo[2] + 0.65 * lengths[2],
        ]
    )
    geometry_entries = []
    refinement_surfaces = []
    refinement_regions = []
    for item in copied:
        name = Path(item["file"]).stem
        geometry_entries.append(
            f"""
    {item["file"]}
    {{
        type triSurfaceMesh;
        name {name};
    }}
"""
        )
        if item["role"] in {"fixed", "design"}:
            refinement_surfaces.append(
                f"""
        {name}
        {{
            level (2 3);
            patchInfo {{ type wall; }}
        }}
"""
            )
        if item["role"] in {"allowed", "forbidden", "root"}:
            refinement_regions.append(
                f"""
        {name}
        {{
            mode inside;
            levels ((1E15 2));
        }}
"""
            )
    return _foam_header("dictionary", "snappyHexMeshDict") + f"""
castellatedMesh true;
snap            true;
addLayers       false;

geometry
{{
{''.join(geometry_entries)}
}};

castellatedMeshControls
{{
    maxLocalCells 200000;
    maxGlobalCells 2000000;
    minRefinementCells 10;
    nCellsBetweenLevels 3;
    resolveFeatureAngle 30;

    features ();

    refinementSurfaces
    {{
{''.join(refinement_surfaces)}
    }}

    refinementRegions
    {{
{''.join(refinement_regions)}
    }}

    locationInMesh ({location[0]:g} {location[1]:g} {location[2]:g});
    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
}}

addLayersControls {{}}

meshQualityControls
{{
    maxNonOrtho 70;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave 80;
    minVol 1e-13;
    minTetQuality 1e-9;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.02;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
}}

debug 0;
mergeTolerance 1e-6;
"""


def _control_dict(config: ProjectConfig, force_patches: list[str]) -> str:
    patch_text = " ".join(force_patches) if force_patches else "frontWing"
    velocity = config.operating_point.velocity_mps
    density = config.operating_point.density
    return _foam_header("dictionary", "controlDict") + f"""
application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         500;
deltaT          1;
writeControl    timeStep;
writeInterval   100;
purgeWrite      2;
writeFormat     ascii;
writePrecision  8;
runTimeModifiable true;

functions
{{
    forceCoeffs
    {{
        type            forceCoeffs;
        libs            ("libforces.so");
        patches         ({patch_text});
        rho             rhoInf;
        rhoInf          {density:g};
        magUInf         {velocity:g};
        lRef            1;
        Aref            1;
        CofR            (0 0 0);
        dragDir         (1 0 0);
        liftDir         (0 0 1);
        pitchAxis       (0 1 0);
        writeControl    timeStep;
        writeInterval   1;
    }}
}}
"""


def _transport_properties(config: ProjectConfig) -> str:
    nu = config.operating_point.viscosity / config.operating_point.density
    return _foam_header("dictionary", "transportProperties") + f"""
transportModel  Newtonian;
nu              [0 2 -1 0 0 0 0] {nu:.8g};
"""


def _turbulence_properties() -> str:
    return _foam_header("dictionary", "turbulenceProperties") + """
simulationType RAS;

RAS
{
    RASModel        kOmegaSST;
    turbulence      on;
    printCoeffs     on;
}
"""


def _field_u(config: ProjectConfig) -> str:
    velocity = config.operating_point.velocity_mps
    return _foam_header("volVectorField", "U", "0") + f"""
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform ({velocity:g} 0 0);
boundaryField
{{
    inlet {{ type fixedValue; value uniform ({velocity:g} 0 0); }}
    outlet {{ type zeroGradient; }}
    sideMin {{ type symmetryPlane; }}
    sideMax {{ type symmetryPlane; }}
    top {{ type symmetryPlane; }}
    bottom {{ type noSlip; }}
    ".*" {{ type noSlip; }}
}}
"""


def _scalar_field(name: str, value: str) -> str:
    dimensions = _scalar_dimensions(name)
    inlet = "zeroGradient" if name == "p" else f"fixedValue; value uniform {value}"
    outlet = f"fixedValue; value uniform {value}" if name == "p" else "zeroGradient"
    wall_type = _wall_scalar_boundary_type(name)
    wall_value = f"; value uniform {value}" if wall_type != "zeroGradient" else ""
    return _foam_header("volScalarField", name, "0") + f"""
dimensions      {dimensions};
internalField   uniform {value};
boundaryField
{{
    inlet {{ type {inlet}; }}
    outlet {{ type {outlet}; }}
    sideMin {{ type symmetryPlane; }}
    sideMax {{ type symmetryPlane; }}
    top {{ type symmetryPlane; }}
    bottom {{ type {wall_type}{wall_value}; }}
    ".*" {{ type {wall_type}{wall_value}; }}
}}
"""


def _scalar_dimensions(name: str) -> str:
    if name in {"p", "k"}:
        return "[0 2 -2 0 0 0 0]"
    if name == "omega":
        return "[0 0 -1 0 0 0 0]"
    if name == "nut":
        return "[0 2 -1 0 0 0 0]"
    return "[0 0 0 0 0 0 0]"


def _wall_scalar_boundary_type(name: str) -> str:
    if name == "k":
        return "kqRWallFunction"
    if name == "omega":
        return "omegaWallFunction"
    if name == "nut":
        return "nutkWallFunction"
    return "zeroGradient"


def _fv_schemes() -> str:
    return _foam_header("dictionary", "fvSchemes") + """
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss upwind;
    div(phi,k) bounded Gauss upwind;
    div(phi,omega) bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
"""


def _fv_solution() -> str:
    return _foam_header("dictionary", "fvSolution") + """
solvers
{
    p { solver GAMG; tolerance 1e-7; relTol 0.01; smoother GaussSeidel; }
    "(U|k|omega)" { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
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
    fields { p 0.3; }
    equations { U 0.7; k 0.7; omega 0.7; }
}
"""


def _decompose_par_dict() -> str:
    return _foam_header("dictionary", "decomposeParDict") + """
numberOfSubdomains 4;
method scotch;
"""


def _allrun() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

blockMesh
surfaceFeatureExtract || true
snappyHexMesh -overwrite
checkMesh -allGeometry -allTopology | tee log.checkMesh
simpleFoam | tee log.simpleFoam
if command -v python3 >/dev/null 2>&1; then
    python3 postprocess_forces.py
elif command -v python >/dev/null 2>&1; then
    python postprocess_forces.py
else
    echo "No Python interpreter found in OpenFOAM runtime; skipping in-container postprocess."
fi
"""


def _allclean() -> str:
    return """#!/usr/bin/env bash
rm -rf constant/polyMesh processor* postProcessing [1-9]* log.* cfd_summary.json
"""


def _allrun_ps1() -> str:
    return """$ErrorActionPreference = "Stop"
wsl bash -lc "cd \"$(wslpath -a \"$PWD\")\" && chmod +x Allrun Allclean && ./Allrun"
"""


def _postprocess_forces_py() -> str:
    return r'''from __future__ import annotations

import json
from pathlib import Path

files = sorted(Path("postProcessing").glob("forceCoeffs*/**/forceCoeffs.dat"))
files.extend(sorted(Path("postProcessing").glob("forceCoeffs*/**/coefficient.dat")))
if not files:
    raise SystemExit("No force coefficient file found.")
files = sorted(files)

last = None
header = []
for line in files[-1].read_text(encoding="utf-8", errors="ignore").splitlines():
    if line.startswith("#"):
        header = line.lstrip("#").split()
        continue
    parts = line.split()
    if parts:
        last = parts

if not last:
    raise SystemExit("forceCoeffs.dat did not contain data rows.")

values = {name: float(value) for name, value in zip(header, last)}
summary = {
    "source": str(files[-1]),
    "latest": values,
    "drag_coefficient": values.get("Cd"),
    "downforce_coefficient": -values["Cl"] if "Cl" in values else None,
}
if summary["drag_coefficient"] is not None and summary["downforce_coefficient"] is not None and abs(summary["drag_coefficient"]) > 1e-12:
    summary["efficiency"] = summary["downforce_coefficient"] / summary["drag_coefficient"]
else:
    summary["efficiency"] = None
Path("cfd_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
'''


def _patch_name(value: str) -> str:
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
