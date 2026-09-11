from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from pathlib import Path
from typing import Mapping

import numpy as np

from .config import GridSpec as _ProjectGridSpec
from .config import MeshRef, OperatingPointSpec, ProjectConfig, RootSpec
from .problem_spec import FlowCaseSpec, ProblemSpec, ResponseSpec, problem_spec_sha256
from .sdf import FieldBundle

_GEOMETRY_ROLES_FOR_ADAPTER = (
    "fixed_solid",
    "initial_design",
    "design_domain",
    "forbidden_region",
    "root",
)


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
    reference = _force_reference(config)
    metadata = _metadata(config, bundle, copied, force_patches, reference)

    files: dict[str, str] = {
        "system/blockMeshDict": _block_mesh_dict(bundle),
        "system/surfaceFeatureExtractDict": _surface_feature_extract_dict(copied),
        "system/snappyHexMeshDict": _snappy_hex_mesh_dict(config, bundle, copied),
        "system/controlDict": _control_dict(config, force_patches, reference),
        "system/fvSchemes": _fv_schemes(config.turbulence_model),
        "system/fvSolution": _fv_solution(config.turbulence_model),
        "system/decomposeParDict": _decompose_par_dict(),
        "constant/transportProperties": _transport_properties(config),
        "constant/turbulenceProperties": _turbulence_properties(config.turbulence_model),
        "0/U": _field_u(config),
        "0/p": _scalar_field("p", "0"),
        **(
            {
                "0/k": _scalar_field("k", "1e-4"),
                "0/omega": _scalar_field("omega", "10"),
                "0/nut": _scalar_field("nut", "0"),
            }
            if config.turbulence_model == "kOmegaSST"
            else {}
        ),
        "Allrun": _allrun(),
        "Allclean": _allclean(),
        "Allrun.ps1": _allrun_ps1(),
        "postprocess_forces.py": _postprocess_forces_py(reference),
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


def problem_spec_to_project_config(
    spec: ProblemSpec,
    *,
    candidate_stl: Path | None = None,
    flow_case_id: str | None = None,
    voxel_size_m: float | None = None,
) -> ProjectConfig:
    """Adapt a native v2 ``ProblemSpec`` into the ``ProjectConfig`` shape ``generate_openfoam_case`` expects.

    This is a body-fitted (Stage V) verification adapter: it maps geometry roles 1:1
    (``fixed_solid -> fixed_solids``, ``design_domain -> design_domains``,
    ``forbidden_region -> forbidden_regions``, ``initial_design -> design_geometry``, ``root -> roots``)
    and derives the operating point from exactly one selected ``flow_cases[]`` entry.

    Fails closed rather than guessing: refuses an ambiguous flow-case selection (more than one
    flow_cases[] entry without an explicit ``flow_case_id``), missing design geometry (no
    ``initial_design`` region and no ``candidate_stl`` override), and any freestream velocity that
    does not resolve to the global +x axis this case template's inlet/outlet patches assume.
    """

    by_role: dict[str, list] = {role: [] for role in _GEOMETRY_ROLES_FOR_ADAPTER}
    for region in spec.geometry_regions:
        by_role[region.role].append(region)

    if candidate_stl is not None:
        design_geometry = [MeshRef(id="candidate", file=candidate_stl.resolve())]
    elif by_role["initial_design"]:
        design_geometry = [MeshRef(id=region.id, file=region.file) for region in by_role["initial_design"]]
    else:
        raise ValueError(
            "ProblemSpec declares no initial_design geometry region and no candidate_stl override "
            "was given; body-fitted case generation needs an explicit design surface to mesh"
        )

    flow_case = _select_flow_case(spec, flow_case_id)
    operating_point = _operating_point_from_flow_case(spec, flow_case)
    turbulence_model = _resolve_turbulence_model(flow_case)
    grid = _ProjectGridSpec(
        voxel_size_m=voxel_size_m if voxel_size_m is not None else spec.grid.voxel_size_m,
        padding_m=spec.grid.padding_m,
    )

    return ProjectConfig(
        path=spec.path,
        fixed_solids=[MeshRef(id=r.id, file=r.file) for r in by_role["fixed_solid"]],
        design_geometry=design_geometry,
        design_domains=[MeshRef(id=r.id, file=r.file) for r in by_role["design_domain"]],
        forbidden_regions=[MeshRef(id=r.id, file=r.file) for r in by_role["forbidden_region"]],
        roots=[RootSpec(id=r.id, type="stl", file=r.file) for r in by_role["root"]],
        grid=grid,
        operating_point=operating_point,
        problem_spec=spec,
        flow_case_id=flow_case.id,
        turbulence_model=turbulence_model,
    )


def _select_flow_case(spec: ProblemSpec, flow_case_id: str | None) -> FlowCaseSpec:
    if flow_case_id is None:
        if len(spec.flow_cases) != 1:
            raise ValueError(
                "ProblemSpec declares more than one flow_cases[] entry; pass an explicit "
                "flow_case_id to select which one this body-fitted case honors"
            )
        return spec.flow_cases[0]
    for flow_case in spec.flow_cases:
        if flow_case.id == flow_case_id:
            return flow_case
    raise ValueError(f"ProblemSpec has no flow_cases[].id == {flow_case_id!r}")


def _operating_point_from_flow_case(spec: ProblemSpec, flow_case: FlowCaseSpec) -> OperatingPointSpec:
    vx, vy, vz = _to_global_vector(spec, flow_case.freestream_velocity_mps)
    tolerance = 1.0e-6 * max(abs(vx), 1.0)
    if vx <= 0.0 or abs(vy) > tolerance or abs(vz) > tolerance:
        raise ValueError(
            "Body-fitted OpenFOAM case generation requires flow_cases[].freestream_velocity_mps to "
            "resolve to the global +x axis (this case template's inlet/outlet patches are fixed along "
            f"x); flow case {flow_case.id!r} resolves to global vector ({vx!r}, {vy!r}, {vz!r})"
        )
    return OperatingPointSpec(
        velocity_mps=vx,
        density=flow_case.fluid.density_kg_m3,
        viscosity=flow_case.fluid.dynamic_viscosity_pa_s,
    )


def _resolve_turbulence_model(flow_case: FlowCaseSpec) -> str:
    """Map a declared flow_case.turbulence.model onto a case template this generator supports.

    Fails closed: only kOmegaSST (the default when turbulence is unspecified, matching this
    template's historical behavior) and laminar are supported. Anything else is refused rather
    than silently coerced.
    """

    if flow_case.turbulence is None:
        return "kOmegaSST"
    normalized = flow_case.turbulence.model.lower().replace("_", "")
    if normalized == "komegasst":
        return "kOmegaSST"
    if normalized == "laminar":
        return "laminar"
    raise ValueError(
        "Body-fitted OpenFOAM case generation only supports turbulence.model kOmegaSST or "
        f"laminar; flow case {flow_case.id!r} declares {flow_case.turbulence.model!r}"
    )


def _copy_stls(config: ProjectConfig, tri_surface_dir: Path) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []

    def record(role: str, item_id: str, src: Path, name: str) -> None:
        shutil.copyfile(src, tri_surface_dir / name)
        copied.append(
            {
                "role": role,
                "id": item_id,
                "file": name,
                "patch": _patch_name(item_id),
                "source_path": str(src),
                "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
            }
        )

    def copy_refs(role: str, refs: list[MeshRef]) -> None:
        for ref in refs:
            src = config.resolve(ref.file)
            record(role, ref.id, src, f"{role}_{_patch_name(ref.id)}.stl")

    copy_refs("fixed", config.fixed_solids)
    copy_refs("design", config.design_geometry)
    copy_refs("allowed", config.design_domains)
    copy_refs("forbidden", config.forbidden_regions)
    for root in config.roots:
        if root.type == "stl" and root.file is not None:
            src = config.resolve(root.file)
            record("root", root.id, src, f"root_{_patch_name(root.id)}.stl")
    return copied


def _metadata(
    config: ProjectConfig,
    bundle: FieldBundle,
    copied: list[dict[str, str]],
    force_patches: list[str],
    reference: Mapping[str, object],
) -> dict[str, object]:
    metadata: dict[str, object] = {
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
            "turbulence_model": config.turbulence_model,
        },
        "force_reference": dict(reference),
        "mesh_refinement": _mesh_refinement_metadata(bundle),
    }
    if config.problem_spec is not None:
        metadata["problem_id"] = config.problem_spec.problem_id
        metadata["problem_spec_sha256"] = problem_spec_sha256(config.problem_spec)
        if config.flow_case_id is not None:
            metadata["flow_case_id"] = config.flow_case_id
    return metadata


def _block_mesh_cell_counts(bundle: FieldBundle) -> tuple[int, int, int]:
    bounds = bundle.grid.bounds
    lengths = bounds[1] - bounds[0]
    cells = np.maximum(np.ceil(lengths / (4.0 * bundle.grid.spacing)).astype(int), 1)
    return int(cells[0]), int(cells[1]), int(cells[2])


def _mesh_refinement_metadata(bundle: FieldBundle) -> dict[str, object]:
    nx, ny, nz = _block_mesh_cell_counts(bundle)
    return {
        "voxel_size_m": bundle.grid.spacing,
        "background_block_mesh_cells": {"nx": nx, "ny": ny, "nz": nz, "total": nx * ny * nz},
    }


def _force_reference(config: ProjectConfig) -> dict[str, object]:
    """Derive body-fitted forceCoeffs reference quantities from the declared ProblemSpec.

    Fails closed: refuses to fall back to Aref=1/lRef=1 when reference_values or the
    drag/downforce response directions are not declared.
    """

    spec = config.problem_spec
    if spec is None or spec.reference_values is None:
        raise ValueError(
            "OpenFOAM case generation requires a project 'reference_values' block "
            "(area_m2, length_m); refusing to default forceCoeffs Aref/lRef to 1"
        )
    area = spec.reference_values.area_m2
    length = spec.reference_values.length_m
    if area is None or length is None:
        raise ValueError(
            "reference_values.area_m2 and reference_values.length_m are both required "
            "for body-fitted forceCoeffs; refusing to default to 1"
        )

    drag_dir = _to_global_direction(spec, _force_response(spec, "drag", config.flow_case_id).direction)
    downforce_dir = _to_global_direction(spec, _force_response(spec, "downforce", config.flow_case_id).direction)
    lift_dir = tuple(0.0 if component == 0.0 else -component for component in downforce_dir)

    density = config.operating_point.density
    speed = config.operating_point.velocity_mps
    factor = 0.5 * density * area * speed * speed
    if not all(isfinite(value) and value > 0.0 for value in (density, area, speed, factor)):
        raise ValueError("Force reference quantities must be finite and positive")

    return {
        "area_m2": area,
        "length_m": length,
        "moment_center_m": spec.reference_values.moment_center_m,
        "drag_dir": drag_dir,
        "lift_dir": lift_dir,
        "density_kg_m3": density,
        "freestream_speed_mps": speed,
        "factor_N_per_coefficient": factor,
    }


def _force_response(spec: ProblemSpec, response_id: str, flow_case_id: str | None = None) -> ResponseSpec:
    for response in spec.responses:
        if (
            response.id == response_id
            and response.kind == "force"
            and response.direction is not None
            and (flow_case_id is None or response.flow_case_id == flow_case_id)
        ):
            return response
    scope = f" for flow_case_id {flow_case_id!r}" if flow_case_id is not None else ""
    raise ValueError(f"ProblemSpec must declare a force response {response_id!r} with a direction{scope}")


def _to_global_vector(spec: ProblemSpec, vector: tuple[float, float, float]) -> tuple[float, float, float]:
    """Resolve a vector declared in the problem's coordinate frame to global axes."""

    basis = spec.coordinate_frame.basis
    x, y, z = vector
    return tuple(x * basis.x[axis] + y * basis.y[axis] + z * basis.z[axis] for axis in range(3))


def _to_global_direction(spec: ProblemSpec, direction: tuple[float, float, float]) -> tuple[float, float, float]:
    """Resolve a response direction (declared in the problem's coordinate frame) to global axes."""

    global_vec = _to_global_vector(spec, direction)
    norm = sqrt(sum(component * component for component in global_vec))
    return tuple(component / norm for component in global_vec)


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
    cells = _block_mesh_cell_counts(bundle)
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


def _control_dict(config: ProjectConfig, force_patches: list[str], reference: Mapping[str, object]) -> str:
    patch_text = " ".join(force_patches) if force_patches else "frontWing"
    velocity = config.operating_point.velocity_mps
    density = config.operating_point.density
    area = reference["area_m2"]
    length = reference["length_m"]
    drag_dir_text = " ".join(f"{component:.10g}" for component in reference["drag_dir"])
    lift_dir_text = " ".join(f"{component:.10g}" for component in reference["lift_dir"])
    moment_center = reference["moment_center_m"] or (0.0, 0.0, 0.0)
    cofr_text = " ".join(f"{component:.10g}" for component in moment_center)
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
        lRef            {length:g};
        Aref            {area:g};
        CofR            ({cofr_text});
        dragDir         ({drag_dir_text});
        liftDir         ({lift_dir_text});
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


def _turbulence_properties(model: str) -> str:
    if model == "laminar":
        body = "simulationType laminar;\n"
    else:
        body = """simulationType RAS;

RAS
{
    RASModel        kOmegaSST;
    turbulence      on;
    printCoeffs     on;
}
"""
    return _foam_header("dictionary", "turbulenceProperties") + "\n" + body


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


def _fv_schemes(model: str) -> str:
    turbulence_divs = (
        "" if model == "laminar" else
        "    div(phi,k) bounded Gauss upwind;\n    div(phi,omega) bounded Gauss upwind;\n"
    )
    return _foam_header("dictionary", "fvSchemes") + f"""
ddtSchemes {{ default steadyState; }}
gradSchemes {{ default Gauss linear; }}
divSchemes
{{
    default none;
    div(phi,U) bounded Gauss upwind;
{turbulence_divs}    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}
laplacianSchemes {{ default Gauss linear corrected; }}
interpolationSchemes {{ default linear; }}
snGradSchemes {{ default corrected; }}
wallDist {{ method meshWave; }}
"""


def _fv_solution(model: str) -> str:
    velocity_pattern = "U" if model == "laminar" else "(U|k|omega)"
    equation_relaxation = "U 0.7;" if model == "laminar" else "U 0.7; k 0.7; omega 0.7;"
    return _foam_header("dictionary", "fvSolution") + f"""
solvers
{{
    p {{ solver GAMG; tolerance 1e-7; relTol 0.01; smoother GaussSeidel; }}
    "{velocity_pattern}" {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }}
}}

SIMPLE
{{
    nNonOrthogonalCorrectors 0;
    consistent yes;
    pRefCell 0;
    pRefValue 0;
}}

relaxationFactors
{{
    fields {{ p 0.3; }}
    equations {{ {equation_relaxation} }}
}}
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


def _postprocess_forces_py(reference: Mapping[str, object]) -> str:
    reference_literal = json.dumps(
        {
            "density_kg_m3": reference["density_kg_m3"],
            "reference_area_m2": reference["area_m2"],
            "reference_length_m": reference["length_m"],
            "freestream_speed_mps": reference["freestream_speed_mps"],
            "factor_N_per_coefficient": reference["factor_N_per_coefficient"],
        }
    )
    return (
        "from __future__ import annotations\n\n"
        "import json\n"
        "from pathlib import Path\n\n"
        f"REFERENCE = json.loads({reference_literal!r})\n"
        + r'''
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
factor = REFERENCE["factor_N_per_coefficient"]
drag_coefficient = values.get("Cd")
downforce_coefficient = -values["Cl"] if "Cl" in values else None
summary = {
    "source": str(files[-1]),
    "latest": values,
    "drag_coefficient": drag_coefficient,
    "downforce_coefficient": downforce_coefficient,
    "drag_N": drag_coefficient * factor if drag_coefficient is not None else None,
    "downforce_N": downforce_coefficient * factor if downforce_coefficient is not None else None,
    "reference": REFERENCE,
}
if summary["drag_coefficient"] is not None and summary["downforce_coefficient"] is not None and abs(summary["drag_coefficient"]) > 1e-12:
    summary["efficiency"] = summary["downforce_coefficient"] / summary["drag_coefficient"]
else:
    summary["efficiency"] = None
Path("cfd_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
'''
    )


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
