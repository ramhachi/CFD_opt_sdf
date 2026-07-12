from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyvista as pv
from scipy.ndimage import gaussian_filter

from .execution import DEFAULT_OPENFOAM_DOCKER_IMAGE, run_openfoam_case
from .fixed_grid_contract import (
    DENSITY_ARRAYS,
    FIXED_GRID_CONTRACT_SCHEMA_VERSION,
    CartesianCellGrid,
    _assert_same_grid,
    _cartesian_grid,
    _grid_from_manifest,
    _read_cell_vti,
    _read_objective,
    _write_cell_vti,
)


FIXED_GRID_PRIMAL_SCHEMA_VERSION = 1

PRIMAL_DENSITY_VARIANTS = (
    "seed",
    "all-fluid",
    "threshold-solid",
    "filtered-perturbation",
)


@dataclass(frozen=True)
class FixedGridDensityState:
    topology_state_json: Path
    output_dir: Path
    state: dict[str, object]
    grid: CartesianCellGrid
    density_vti: Path
    arrays: dict[str, np.ndarray]


@dataclass(frozen=True)
class FixedGridPrimalCaseArtifacts:
    case_dir: Path
    topology_state_json: Path
    density_vti: Path
    input_density_vti: Path
    case_metadata_json: Path
    primal_summary_json: Path
    density_variant: str
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "case_dir",
            "topology_state_json",
            "density_vti",
            "input_density_vti",
            "case_metadata_json",
            "primal_summary_json",
        ):
            data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class FixedGridPrimalSuiteArtifacts:
    run_dir: Path
    topology_state_json: Path
    summary_json: Path
    summary_markdown: Path
    history_csv: Path
    cases: list[FixedGridPrimalCaseArtifacts]
    summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "run_dir",
            "topology_state_json",
            "summary_json",
            "summary_markdown",
            "history_csv",
        ):
            data[key] = str(data[key])
        data["cases"] = [case.to_dict() for case in self.cases]
        return data


def load_fixed_grid_density_state(topology_state_json: Path) -> FixedGridDensityState:
    topology_state_json = topology_state_json.resolve()
    output_dir = topology_state_json.parent
    state = json.loads(topology_state_json.read_text(encoding="utf-8"))
    if state.get("schema_version") != FIXED_GRID_CONTRACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported fixed-grid schema_version: {state.get('schema_version')!r}"
        )
    if state.get("kind") != "fixed_grid_topology_state":
        raise ValueError(f"Unsupported topology state kind: {state.get('kind')!r}")

    density_path = _resolve_manifest_path(output_dir, state.get("density_vti"))
    grid, arrays = _read_cell_vti(density_path, expected_kind="fixed_grid_density")
    missing = sorted(set(DENSITY_ARRAYS) - set(arrays))
    if missing:
        raise ValueError(f"density.vti is missing arrays: {', '.join(missing)}")

    manifest_grid = _grid_from_manifest(dict(state.get("grid") or {}))
    _assert_same_grid(grid, manifest_grid, "density.vti", "topology_state.json")
    return FixedGridDensityState(
        topology_state_json=topology_state_json,
        output_dir=output_dir,
        state=state,
        grid=grid,
        density_vti=density_path,
        arrays=arrays,
    )


def prepare_fixed_grid_primal_case(
    topology_state_json: Path,
    *,
    case_dir: Path,
    template_case_dir: Path | None = None,
    density_variant: str = "seed",
    overwrite: bool = False,
    perturbation_seed: int = 1,
    perturbation_amplitude: float = 0.05,
    smoothing_radius_cells: float = 1.0,
    solid_threshold: float = 0.5,
    adjoint_iterations: int = 1,
    docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE,
) -> FixedGridPrimalCaseArtifacts:
    if density_variant not in PRIMAL_DENSITY_VARIANTS:
        raise ValueError(
            f"Unsupported density variant {density_variant!r}; "
            f"expected one of {', '.join(PRIMAL_DENSITY_VARIANTS)}"
        )
    if perturbation_amplitude < 0:
        raise ValueError("perturbation_amplitude must be non-negative")
    if smoothing_radius_cells < 0:
        raise ValueError("smoothing_radius_cells must be non-negative")
    if not (0.0 <= solid_threshold <= 1.0):
        raise ValueError("solid_threshold must be within [0, 1]")
    if adjoint_iterations < 0:
        raise ValueError("adjoint_iterations must be non-negative")

    density_state = load_fixed_grid_density_state(topology_state_json)
    template = _resolve_template_case(density_state, template_case_dir)
    resolved_case = case_dir.resolve()
    _prepare_case_directory(resolved_case, overwrite=overwrite)
    _copy_case_template(template, resolved_case)

    raw_density = _variant_density(
        density_state,
        density_variant=density_variant,
        perturbation_seed=perturbation_seed,
        perturbation_amplitude=perturbation_amplitude,
        smoothing_radius_cells=smoothing_radius_cells,
        solid_threshold=solid_threshold,
    )
    density = _apply_hard_masks(raw_density, density_state.arrays)
    fixed_zero_mask = _fixed_zero_mask(density, density_state.arrays)
    ordering = _openfoam_ordering(density_state, template)
    openfoam_density = density[ordering]
    fixed_zero_labels = np.flatnonzero(fixed_zero_mask[ordering]).astype(np.int64)

    _write_block_mesh_dict(resolved_case / "system" / "blockMeshDict", density_state.grid)
    _write_alpha_field(
        resolved_case / "0.orig" / "alpha",
        openfoam_density,
        boundary_text=_read_alpha_boundary_template(template),
    )
    _write_fixed_zero_labels(resolved_case, fixed_zero_labels)
    _write_cell_zone_writers(resolved_case)
    _write_allrun(resolved_case)
    _write_allclean(resolved_case)
    _patch_optimisation_dict(
        resolved_case / "system" / "optimisationDict",
        fixed_zero_zone_name="fixedZeroFromMask",
        adjoint_iterations=adjoint_iterations,
    )
    library_path = _copy_custom_objective_library(resolved_case)
    _patch_control_dict_libraries(
        resolved_case / "system" / "controlDict",
        library_path=library_path,
    )

    input_density_vti = resolved_case / "fixed_grid_input_density.vti"
    _write_cell_vti(
        density_state.grid,
        {
            "rho_input": density.astype(np.float32),
            "rho_contract": np.asarray(density_state.arrays["rho"], dtype=np.float32),
            "rho_projected_contract": np.asarray(
                density_state.arrays["rho_projected"],
                dtype=np.float32,
            ),
            "fixed_zero_mask": fixed_zero_mask.astype(np.uint8),
            "active_design_mask": np.asarray(
                density_state.arrays["active_design_mask"],
                dtype=np.uint8,
            ),
        },
        input_density_vti,
        kind="fixed_grid_primal_input",
    )

    metadata = _case_metadata(
        density_state,
        case_dir=resolved_case,
        template_case_dir=template,
        density_variant=density_variant,
        density=density,
        raw_density=raw_density,
        fixed_zero_mask=fixed_zero_mask,
        fixed_zero_labels=fixed_zero_labels,
        ordering=ordering,
        perturbation_seed=perturbation_seed,
        perturbation_amplitude=perturbation_amplitude,
        smoothing_radius_cells=smoothing_radius_cells,
        solid_threshold=solid_threshold,
        adjoint_iterations=adjoint_iterations,
        docker_image=docker_image,
        library_path=library_path,
    )
    case_metadata_json = resolved_case / "fixed_grid_primal_case_metadata.json"
    case_metadata_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    summary = summarize_fixed_grid_primal_case(
        resolved_case,
        topology_state_json=density_state.topology_state_json,
        status_override="prepared",
        docker_image=docker_image,
    )
    return FixedGridPrimalCaseArtifacts(
        case_dir=resolved_case,
        topology_state_json=density_state.topology_state_json,
        density_vti=density_state.density_vti,
        input_density_vti=input_density_vti,
        case_metadata_json=case_metadata_json,
        primal_summary_json=resolved_case / "fixed_grid_primal_summary.json",
        density_variant=density_variant,
        summary=summary,
    )


def run_fixed_grid_primal_case(
    topology_state_json: Path,
    *,
    case_dir: Path,
    template_case_dir: Path | None = None,
    density_variant: str = "seed",
    backend: str = "auto",
    execute: bool = False,
    timeout_seconds: int | None = None,
    overwrite: bool = False,
    perturbation_seed: int = 1,
    perturbation_amplitude: float = 0.05,
    smoothing_radius_cells: float = 1.0,
    solid_threshold: float = 0.5,
    adjoint_iterations: int = 1,
    docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE,
) -> FixedGridPrimalCaseArtifacts:
    artifacts = prepare_fixed_grid_primal_case(
        topology_state_json,
        case_dir=case_dir,
        template_case_dir=template_case_dir,
        density_variant=density_variant,
        overwrite=overwrite,
        perturbation_seed=perturbation_seed,
        perturbation_amplitude=perturbation_amplitude,
        smoothing_radius_cells=smoothing_radius_cells,
        solid_threshold=solid_threshold,
        adjoint_iterations=adjoint_iterations,
        docker_image=docker_image,
    )
    run_result = run_openfoam_case(
        artifacts.case_dir,
        backend=backend,
        dry_run=not execute,
        timeout_seconds=timeout_seconds,
        docker_image=docker_image,
    )
    summary = summarize_fixed_grid_primal_case(
        artifacts.case_dir,
        topology_state_json=artifacts.topology_state_json,
        run_result=run_result.to_dict(),
        docker_image=docker_image,
    )
    return FixedGridPrimalCaseArtifacts(
        case_dir=artifacts.case_dir,
        topology_state_json=artifacts.topology_state_json,
        density_vti=artifacts.density_vti,
        input_density_vti=artifacts.input_density_vti,
        case_metadata_json=artifacts.case_metadata_json,
        primal_summary_json=artifacts.primal_summary_json,
        density_variant=artifacts.density_variant,
        summary=summary,
    )


def run_fixed_grid_primal_suite(
    topology_state_json: Path,
    *,
    run_dir: Path,
    template_case_dir: Path | None = None,
    backend: str = "auto",
    execute: bool = False,
    timeout_seconds: int | None = None,
    overwrite: bool = False,
    include_reproducibility_repeat: bool = True,
    perturbation_seed: int = 1,
    perturbation_amplitude: float = 0.05,
    smoothing_radius_cells: float = 1.0,
    solid_threshold: float = 0.5,
    adjoint_iterations: int = 1,
    docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE,
    reproducibility_tolerance: float = 1.0e-10,
) -> FixedGridPrimalSuiteArtifacts:
    if reproducibility_tolerance < 0:
        raise ValueError("reproducibility_tolerance must be non-negative")
    run_dir = run_dir.resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        marker = run_dir / "fixed_grid_primal_suite_summary.json"
        if not overwrite or not marker.exists():
            raise FileExistsError(
                f"{run_dir} already exists. Use overwrite=True for a generated suite."
            )
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    variants: list[tuple[str, str]] = [
        ("all_fluid", "all-fluid"),
        ("threshold_solid", "threshold-solid"),
        ("seed", "seed"),
        ("filtered_perturbation", "filtered-perturbation"),
    ]
    if include_reproducibility_repeat:
        variants.append(("seed_repeat", "seed"))

    cases: list[FixedGridPrimalCaseArtifacts] = []
    for name, variant in variants:
        case = run_fixed_grid_primal_case(
            topology_state_json,
            case_dir=run_dir / name,
            template_case_dir=template_case_dir,
            density_variant=variant,
            backend=backend,
            execute=execute,
            timeout_seconds=timeout_seconds,
            overwrite=True,
            perturbation_seed=perturbation_seed,
            perturbation_amplitude=perturbation_amplitude,
            smoothing_radius_cells=smoothing_radius_cells,
            solid_threshold=solid_threshold,
            adjoint_iterations=adjoint_iterations,
            docker_image=docker_image,
        )
        cases.append(case)

    summary = _suite_summary(
        run_dir,
        topology_state_json=Path(topology_state_json).resolve(),
        cases=cases,
        execute=execute,
        backend=backend,
        docker_image=docker_image,
        reproducibility_tolerance=reproducibility_tolerance,
    )
    history_csv = run_dir / "fixed_grid_primal_suite_history.csv"
    _write_suite_history(history_csv, cases)
    summary_json = run_dir / "fixed_grid_primal_suite_summary.json"
    summary_markdown = run_dir / "fixed_grid_primal_suite_summary.md"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary_markdown.write_text(_suite_markdown(summary), encoding="utf-8")
    return FixedGridPrimalSuiteArtifacts(
        run_dir=run_dir,
        topology_state_json=Path(topology_state_json).resolve(),
        summary_json=summary_json,
        summary_markdown=summary_markdown,
        history_csv=history_csv,
        cases=cases,
        summary=summary,
    )


def summarize_fixed_grid_primal_case(
    case_dir: Path,
    *,
    topology_state_json: Path | None = None,
    run_result: dict[str, object] | None = None,
    status_override: str | None = None,
    efficiency_min: float = 3.0,
    docker_image: str = DEFAULT_OPENFOAM_DOCKER_IMAGE,
) -> dict[str, object]:
    case_dir = case_dir.resolve()
    metadata_path = case_dir / "fixed_grid_primal_case_metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else {}
    )
    log_text = _read_text_if_exists(case_dir / "log.adjointOptimisationFoam")
    convergence = _parse_convergence(log_text)
    residual_history = _parse_residual_history(log_text)
    continuity_history = _parse_continuity_history(log_text)
    force_history = _parse_force_history(log_text)
    _write_history_csv(case_dir / "fixed_grid_residual_history.csv", residual_history)
    _write_history_csv(case_dir / "fixed_grid_mass_balance_history.csv", continuity_history)
    _write_history_csv(case_dir / "fixed_grid_force_history.csv", force_history)

    drag = _try_read_objective(case_dir, "drag")
    downforce = _try_read_objective(case_dir, "downforce")
    run_ok = None if run_result is None else bool(run_result.get("ok"))
    solver_completed = _solver_completed(log_text)
    if status_override is not None:
        status = status_override
    elif run_result is not None and not run_ok:
        status = "failed"
    elif drag is not None and downforce is not None and solver_completed:
        status = "converged" if convergence["primal_converged"] else "completed"
    elif run_result is not None and run_result.get("dry_run"):
        status = "dry_run"
    else:
        status = "not_executed"

    drag_value = drag["value"] if drag else None
    downforce_value = downforce["value"] if downforce else None
    efficiency = (
        downforce_value / drag_value
        if drag_value is not None
        and downforce_value is not None
        and abs(drag_value) > 1.0e-30
        else None
    )
    efficiency_constraint = (
        efficiency_min * drag_value - downforce_value
        if drag_value is not None and downforce_value is not None
        else None
    )
    summary = {
        "schema_version": FIXED_GRID_PRIMAL_SCHEMA_VERSION,
        "kind": "fixed_grid_primal_summary",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "case_dir": str(case_dir),
        "topology_state_json": str(Path(topology_state_json).resolve())
        if topology_state_json is not None
        else metadata.get("topology_state_json"),
        "density_variant": metadata.get("density_variant"),
        "source_solver": {
            "backend": "openfoam-topO",
            "solver": "adjointOptimisationFoam",
            "version": "2512",
            "docker_image": docker_image,
            "mesh_policy": "fixed",
            "remeshing_per_iteration": False,
        },
        "objective_definition": "minimize -C_DF",
        "constraint_definition": "efficiency_min*C_D-C_DF <= 0",
        "sign_convention": {
            "drag": "positive in +X",
            "downforce": "positive in -Z",
            "objective": "negative downforce; lower is better",
            "efficiency_constraint": "non-positive is feasible",
        },
        "units": {
            "drag_coefficient": "1",
            "downforce_coefficient": "1",
            "objective": "1",
            "efficiency_constraint": "1",
        },
        "efficiency_min": efficiency_min,
        "drag_coefficient": drag_value,
        "downforce_coefficient": downforce_value,
        "objective": -downforce_value if downforce_value is not None else None,
        "efficiency": efficiency,
        "efficiency_constraint": efficiency_constraint,
        "convergence": convergence,
        "history": {
            "residual_csv": "fixed_grid_residual_history.csv",
            "mass_balance_csv": "fixed_grid_mass_balance_history.csv",
            "force_csv": "fixed_grid_force_history.csv",
            "residual_rows": len(residual_history),
            "mass_balance_rows": len(continuity_history),
            "force_rows": len(force_history),
            "last_residual": residual_history[-1] if residual_history else None,
            "last_mass_balance": continuity_history[-1] if continuity_history else None,
            "last_force": force_history[-1] if force_history else None,
        },
        "density_input": metadata.get("density_input"),
        "mask_counts": metadata.get("mask_counts"),
        "openfoam_run": run_result,
        "objective_files": {
            "drag": drag["path"] if drag else None,
            "downforce": downforce["path"] if downforce else None,
        },
    }
    summary_path = case_dir / "fixed_grid_primal_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _resolve_manifest_path(directory: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else directory / path


def _resolve_template_case(
    density_state: FixedGridDensityState,
    template_case_dir: Path | None,
) -> Path:
    candidates: list[Path] = []
    if template_case_dir is not None:
        candidates.append(Path(template_case_dir))
    source_solver = dict(density_state.state.get("source_solver") or {})
    source_case = source_solver.get("case_dir")
    if source_case:
        candidates.append(Path(str(source_case)))
    candidates.append(Path("examples/fixed_grid_backend_spike/openfoam/porous_force_3d_fd_base"))
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "system" / "optimisationDict").exists():
            return resolved
    raise FileNotFoundError("Could not locate an OpenFOAM fixed-grid template case")


def _prepare_case_directory(case_dir: Path, *, overwrite: bool) -> None:
    if not case_dir.exists():
        case_dir.mkdir(parents=True)
        return
    if not any(case_dir.iterdir()):
        return
    metadata = case_dir / "fixed_grid_primal_case_metadata.json"
    if not overwrite or not metadata.exists():
        raise FileExistsError(
            f"{case_dir} already exists. Use overwrite=True for a generated case."
        )
    data = json.loads(metadata.read_text(encoding="utf-8"))
    if data.get("kind") != "fixed_grid_primal_case":
        raise FileExistsError(f"{case_dir} does not look like a generated T2 case")
    shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)


def _copy_case_template(template_case_dir: Path, case_dir: Path) -> None:
    for relative in ("0.orig", "constant", "system"):
        source = template_case_dir / relative
        target = case_dir / relative
        if source.exists():
            shutil.copytree(source, target)
        else:
            target.mkdir(parents=True, exist_ok=True)
    for relative in ("0", "1", "processor0", "processor1", "processor2", "processor3", "VTK", "optimisation"):
        target = case_dir / relative
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
    (case_dir / "0.orig").mkdir(parents=True, exist_ok=True)
    (case_dir / "constant").mkdir(parents=True, exist_ok=True)
    (case_dir / "system").mkdir(parents=True, exist_ok=True)


def _variant_density(
    density_state: FixedGridDensityState,
    *,
    density_variant: str,
    perturbation_seed: int,
    perturbation_amplitude: float,
    smoothing_radius_cells: float,
    solid_threshold: float,
) -> np.ndarray:
    rho = np.asarray(density_state.arrays["rho"], dtype=np.float64)
    if density_variant == "seed":
        return rho.copy()
    if density_variant == "all-fluid":
        return np.zeros_like(rho)
    if density_variant == "threshold-solid":
        return (rho >= solid_threshold).astype(np.float64)
    if density_variant == "filtered-perturbation":
        active = np.asarray(density_state.arrays["active_design_mask"]) > 0
        shape = density_state.grid.cell_shape
        rng = np.random.default_rng(perturbation_seed)
        noise = rng.normal(0.0, 1.0, size=shape)
        if smoothing_radius_cells > 0:
            noise = gaussian_filter(noise, sigma=smoothing_radius_cells, mode="nearest")
        flat_noise = noise.ravel(order="F")
        selected = flat_noise[active]
        if selected.size and np.max(np.abs(selected)) > 1.0e-30:
            flat_noise = flat_noise / float(np.max(np.abs(selected)))
        perturbation = perturbation_amplitude * flat_noise
        return np.clip(rho + perturbation * active.astype(np.float64), 0.0, 1.0)
    raise ValueError(f"Unsupported density variant: {density_variant}")


def _apply_hard_masks(
    density: np.ndarray,
    arrays: dict[str, np.ndarray],
) -> np.ndarray:
    values = np.asarray(density, dtype=np.float64).copy()
    allowed = np.asarray(arrays["allowed_mask"]) > 0
    forbidden = np.asarray(arrays["forbidden_mask"]) > 0
    fixed_solid = np.asarray(arrays["fixed_solid_mask"]) > 0
    values[~allowed & ~fixed_solid] = 0.0
    values[forbidden] = 0.0
    values[fixed_solid] = 1.0
    return np.clip(values, 0.0, 1.0)


def _fixed_zero_mask(
    density: np.ndarray,
    arrays: dict[str, np.ndarray],
) -> np.ndarray:
    allowed = np.asarray(arrays["allowed_mask"]) > 0
    forbidden = np.asarray(arrays["forbidden_mask"]) > 0
    fixed_solid = np.asarray(arrays["fixed_solid_mask"]) > 0
    active = np.asarray(arrays["active_design_mask"]) > 0
    zero_density = np.asarray(density) <= 1.0e-12
    return forbidden | (~allowed & ~fixed_solid) | (~active & ~fixed_solid & zero_density)


def _openfoam_ordering(
    density_state: FixedGridDensityState,
    template_case_dir: Path,
) -> np.ndarray:
    source_solver = dict(density_state.state.get("source_solver") or {})
    vtk_candidates = []
    if source_solver.get("initial_vtk"):
        vtk_candidates.append(Path(str(source_solver["initial_vtk"])))
    vtk_candidates.extend(sorted((template_case_dir / "VTK").glob("**/internal.vtu")))
    for path in vtk_candidates:
        if not path.exists():
            continue
        mesh = pv.read(path)
        try:
            grid, flat_indices = _cartesian_grid(mesh)
            _assert_same_grid(density_state.grid, grid, "density.vti", str(path))
        except ValueError:
            continue
        return flat_indices.astype(np.int64)
    return np.arange(density_state.grid.cell_count, dtype=np.int64)


def _write_block_mesh_dict(path: Path, grid: CartesianCellGrid) -> None:
    lower, upper = grid.bounds
    nx, ny, nz = grid.cell_shape
    vertices = (
        (lower[0], lower[1], lower[2]),
        (upper[0], lower[1], lower[2]),
        (upper[0], upper[1], lower[2]),
        (lower[0], upper[1], lower[2]),
        (lower[0], lower[1], upper[2]),
        (upper[0], lower[1], upper[2]),
        (upper[0], upper[1], upper[2]),
        (lower[0], upper[1], upper[2]),
    )
    vertex_text = "\n".join(f"    ({x:.12g} {y:.12g} {z:.12g})" for x, y, z in vertices)
    path.write_text(
        _foam_header("dictionary", "blockMeshDict")
        + f"""
scale 1;

vertices
(
{vertex_text}
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces ((0 4 7 3));
    }}
    outlet
    {{
        type patch;
        faces ((1 2 6 5));
    }}
    spanMin
    {{
        type symmetryPlane;
        faces ((0 1 5 4));
    }}
    spanMax
    {{
        type symmetryPlane;
        faces ((3 7 6 2));
    }}
    lower
    {{
        type symmetryPlane;
        faces ((0 3 2 1));
    }}
    upper
    {{
        type symmetryPlane;
        faces ((4 5 6 7));
    }}
);

mergePatchPairs
(
);
""",
        encoding="utf-8",
        newline="\n",
    )


def _read_alpha_boundary_template(template_case_dir: Path) -> str:
    for path in (template_case_dir / "0.orig" / "alpha", template_case_dir / "0" / "alpha"):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"\nboundaryField\s*\{(?P<body>.*)\}\s*$", text, flags=re.DOTALL)
        if match:
            return "boundaryField\n{" + match.group("body") + "}\n"
    return """boundaryField
{
    inlet { type zeroGradient; }
    outlet { type zeroGradient; }
    spanMin { type symmetryPlane; }
    spanMax { type symmetryPlane; }
    lower { type symmetryPlane; }
    upper { type symmetryPlane; }
}
"""


def _write_alpha_field(path: Path, values: np.ndarray, *, boundary_text: str) -> None:
    value_text = "\n".join(f"{float(value):.12g}" for value in values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _foam_header("volScalarField", "alpha", location="0")
        + f"""
dimensions      [0 0 0 0 0 0 0];

internalField   nonuniform List<scalar>
{values.size}
(
{value_text}
)
;

{boundary_text}
""",
        encoding="utf-8",
        newline="\n",
    )


def _write_fixed_zero_labels(case_dir: Path, labels: np.ndarray) -> None:
    directory = case_dir / "constant" / "fixedGridMask"
    directory.mkdir(parents=True, exist_ok=True)
    text = "\n".join(str(int(value)) for value in labels)
    (directory / "fixed_zero_labels.txt").write_text(text + ("\n" if text else ""), encoding="utf-8")


def _write_cell_zone_writers(case_dir: Path) -> None:
    (case_dir / "write_fixed_grid_cell_zones.sh").write_text(
        r'''#!/bin/sh
set -eu

labels_path="constant/fixedGridMask/fixed_zero_labels.txt"
zone_path="constant/polyMesh/cellZones"
if [ -f "$labels_path" ]; then
    count="$(grep -cve '^[[:space:]]*$' "$labels_path" || true)"
else
    count="0"
fi

{
cat <<EOF
FoamFile
{
    version     2.0;
    format      ascii;
    class       regIOobject;
    location    "constant/polyMesh";
    object      cellZones;
}

1
(
fixedZeroFromMask
{
    type            cellZone;
    cellLabels      List<label>
$count
(
EOF
if [ -f "$labels_path" ]; then
    cat "$labels_path"
fi
cat <<EOF
)
    ;
}
)
EOF
} > "$zone_path"

echo "Wrote $zone_path with $count fixed-zero cells"
''',
        encoding="utf-8",
        newline="\n",
    )
    (case_dir / "write_fixed_grid_cell_zones.py").write_text(
        r'''from __future__ import annotations

from pathlib import Path

labels_path = Path("constant/fixedGridMask/fixed_zero_labels.txt")
labels = []
if labels_path.exists():
    labels = [int(line) for line in labels_path.read_text(encoding="utf-8").splitlines() if line.strip()]

body = "\n".join(str(label) for label in labels)
text = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       regIOobject;
    location    "constant/polyMesh";
    object      cellZones;
}}

1
(
fixedZeroFromMask
{{
    type            cellZone;
    cellLabels      List<label>
{len(labels)}
(
{body}
)
    ;
}}
)
"""

path = Path("constant/polyMesh/cellZones")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(text, encoding="utf-8")
print(f"Wrote {path} with {len(labels)} fixed-zero cells")
''',
        encoding="utf-8",
        newline="\n",
    )


def _write_allrun(case_dir: Path) -> None:
    (case_dir / "Allrun").write_text(
        """#!/bin/sh
set -e
cd "${0%/*}" || exit

if [ -z "${WM_PROJECT_DIR:-}" ]; then
    if [ -f /usr/lib/openfoam/openfoam2512/etc/bashrc ]; then
        . /usr/lib/openfoam/openfoam2512/etc/bashrc
    elif [ -f /opt/openfoam*/etc/bashrc ]; then
        . /opt/openfoam*/etc/bashrc
    fi
fi
. ${WM_PROJECT_DIR:?}/bin/tools/RunFunctions

export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
export FOAM_USER_LIBBIN="${FOAM_USER_LIBBIN:-$PWD/lib}"
export LD_LIBRARY_PATH="$FOAM_USER_LIBBIN:${LD_LIBRARY_PATH:-}"

restore0Dir

runApplication blockMesh
sh write_fixed_grid_cell_zones.sh
runApplication decomposePar -no-libs
runParallel $(getApplication)
runApplication reconstructPar -latestTime -no-libs
runApplication foamToVTK -no-libs -latestTime -fields "(alpha alphaTilda beta U p)"
""",
        encoding="utf-8",
        newline="\n",
    )


def _write_allclean(case_dir: Path) -> None:
    (case_dir / "Allclean").write_text(
        """#!/bin/sh
rm -rf 0 [1-9]* processor* VTK postProcessing optimisation log.* openfoam_run_summary.json
""",
        encoding="utf-8",
        newline="\n",
    )


def _patch_optimisation_dict(
    path: Path,
    *,
    fixed_zero_zone_name: str,
    adjoint_iterations: int,
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(
        r"fixedZeroPorousZones\s*\([^;]*?\)\s*;",
        f"fixedZeroPorousZones\n        (\n            {fixed_zero_zone_name}\n        );",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"\bnIters\s+4000\s*;",
        f"nIters {adjoint_iterations};",
        text,
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def _patch_control_dict_libraries(path: Path, *, library_path: str | None) -> None:
    if not path.exists() or library_path is None:
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    libs_line = 'libs            ("./lib/libcfdSdfPorousObjectives.so");'
    if re.search(r"(?m)^\s*libs\s+", text):
        text = re.sub(r"(?m)^\s*libs\s+.*?;\s*$", libs_line, text)
    else:
        text = re.sub(
            r"(?m)^application\s+.*?;\s*$",
            lambda match: match.group(0) + "\n\n" + libs_line,
            text,
            count=1,
        )
    path.write_text(text, encoding="utf-8", newline="\n")


def _copy_custom_objective_library(case_dir: Path) -> str | None:
    candidates = [
        Path("openfoam_extensions/porousDirectionalForce/lib/libcfdSdfPorousObjectives.so"),
        case_dir.parent.parent.parent / "openfoam_extensions" / "porousDirectionalForce" / "lib" / "libcfdSdfPorousObjectives.so",
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            target_dir = case_dir / "lib"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / resolved.name
            shutil.copyfile(resolved, target)
            return str(target)
    return None


def _case_metadata(
    density_state: FixedGridDensityState,
    *,
    case_dir: Path,
    template_case_dir: Path,
    density_variant: str,
    density: np.ndarray,
    raw_density: np.ndarray,
    fixed_zero_mask: np.ndarray,
    fixed_zero_labels: np.ndarray,
    ordering: np.ndarray,
    perturbation_seed: int,
    perturbation_amplitude: float,
    smoothing_radius_cells: float,
    solid_threshold: float,
    adjoint_iterations: int,
    docker_image: str,
    library_path: str | None,
) -> dict[str, object]:
    arrays = density_state.arrays
    return {
        "schema_version": FIXED_GRID_PRIMAL_SCHEMA_VERSION,
        "kind": "fixed_grid_primal_case",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_dir": str(case_dir),
        "template_case_dir": str(template_case_dir),
        "topology_state_json": str(density_state.topology_state_json),
        "density_vti": str(density_state.density_vti),
        "density_variant": density_variant,
        "grid": density_state.grid.to_dict(),
        "density_input": {
            "array": "rho_input",
            "hash_sha256_float32": _array_hash(density),
            "raw_hash_sha256_float32": _array_hash(raw_density),
            "statistics": _array_stats(density),
            "raw_statistics": _array_stats(raw_density),
            "variant_controls": {
                "perturbation_seed": perturbation_seed,
                "perturbation_amplitude": perturbation_amplitude,
                "smoothing_radius_cells": smoothing_radius_cells,
                "solid_threshold": solid_threshold,
            },
        },
        "mask_counts": {
            "allowed": int(np.count_nonzero(arrays["allowed_mask"])),
            "forbidden": int(np.count_nonzero(arrays["forbidden_mask"])),
            "fixed_solid": int(np.count_nonzero(arrays["fixed_solid_mask"])),
            "root": int(np.count_nonzero(arrays["root_mask"])),
            "active_design": int(np.count_nonzero(arrays["active_design_mask"])),
            "fixed_zero": int(np.count_nonzero(fixed_zero_mask)),
            "fixed_zero_openfoam_labels": int(fixed_zero_labels.size),
        },
        "openfoam_mapping": {
            "contract_order": "vtk-x-fastest",
            "internal_field_order": "OpenFOAM cell label order",
            "ordering_hash_sha256_int64": _array_hash(ordering.astype(np.int64)),
            "ordering_source": "source VTK cell centers if available, otherwise identity",
        },
        "source_solver": {
            "backend": "openfoam-topO",
            "solver": "adjointOptimisationFoam",
            "version": "2512",
            "docker_image": docker_image,
            "mesh_policy": "fixed",
            "remeshing_per_iteration": False,
            "adjoint_iterations": adjoint_iterations,
            "custom_objective_library": library_path,
        },
        "run_policy": {
            "uses_stl_extraction": False,
            "uses_remeshing": False,
            "uses_setFields": False,
            "cell_zones_source": "fixed-grid role masks",
        },
    }


def _try_read_objective(case_dir: Path, objective_name: str) -> dict[str, object] | None:
    try:
        path, value = _read_objective(case_dir, objective_name)
    except (FileNotFoundError, ValueError):
        return None
    return {"path": str(path), "value": value}


def _parse_convergence(log_text: str) -> dict[str, object]:
    def iteration(pattern: str) -> int | None:
        match = re.search(pattern, log_text)
        return int(match.group(1)) if match else None

    primal = iteration(r"op1 solution converged in (\d+) iterations")
    drag = iteration(r"as1 solution converged in (\d+) iterations")
    downforce = iteration(r"downforce solution converged in (\d+) iterations")
    fatal = _fatal_patterns(log_text)
    return {
        "completed": _solver_completed(log_text),
        "fatal_patterns": fatal,
        "primal_converged": primal is not None,
        "drag_adjoint_converged": drag is not None,
        "downforce_adjoint_converged": downforce is not None,
        "primal_iterations": primal,
        "drag_adjoint_iterations": drag,
        "downforce_adjoint_iterations": downforce,
    }


def _parse_residual_history(log_text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    pattern = re.compile(
        r"Solving for ([A-Za-z0-9_.*+-]+), Initial residual = ([-+0-9.eE]+), "
        r"Final residual = ([-+0-9.eE]+), No Iterations (\d+)"
    )
    for index, match in enumerate(pattern.finditer(log_text)):
        rows.append(
            {
                "index": index,
                "field": match.group(1),
                "initial_residual": float(match.group(2)),
                "final_residual": float(match.group(3)),
                "iterations": int(match.group(4)),
            }
        )
    return rows


def _parse_continuity_history(log_text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    pattern = re.compile(
        r"time step continuity errors\s*:\s*sum local = ([-+0-9.eE]+), "
        r"global = ([-+0-9.eE]+), cumulative = ([-+0-9.eE]+)"
    )
    for index, match in enumerate(pattern.finditer(log_text)):
        rows.append(
            {
                "index": index,
                "sum_local": float(match.group(1)),
                "global": float(match.group(2)),
                "cumulative": float(match.group(3)),
            }
        )
    return rows


def _parse_force_history(log_text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    latest: dict[str, float] = {}
    for line in log_text.splitlines():
        match = re.match(r"^\s*(drag|downforce)\s*:\s*([-+0-9.eE]+)\s*$", line)
        if not match:
            continue
        latest[match.group(1)] = float(match.group(2))
        if "drag" in latest and "downforce" in latest:
            drag = latest["drag"]
            downforce = latest["downforce"]
            rows.append(
                {
                    "index": len(rows),
                    "drag": drag,
                    "downforce": downforce,
                    "efficiency": downforce / drag
                    if abs(drag) > 1.0e-30
                    else None,
                }
            )
            latest = {}
    return rows


def _solver_completed(log_text: str) -> bool:
    return "\nEnd\n" in log_text and "Finalising parallel run" in log_text and not _fatal_patterns(log_text)


def _fatal_patterns(log_text: str) -> list[str]:
    patterns = (
        "FOAM FATAL",
        "mpirun has detected an attempt to run as root",
        "Segmentation fault",
        "Floating point exception (core dumped)",
        "Floating point exception (8)",
    )
    lowered = log_text.lower()
    return [pattern for pattern in patterns if pattern.lower() in lowered]


def _write_history_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _suite_summary(
    run_dir: Path,
    *,
    topology_state_json: Path,
    cases: list[FixedGridPrimalCaseArtifacts],
    execute: bool,
    backend: str,
    docker_image: str,
    reproducibility_tolerance: float,
) -> dict[str, object]:
    statuses = [case.summary.get("status") for case in cases]
    seed_cases = [
        case
        for case in cases
        if case.summary.get("density_variant") == "seed"
        and case.case_dir.name in {"seed", "seed_repeat"}
    ]
    reproducibility = {
        "status": "not_available",
        "tolerance": reproducibility_tolerance,
        "compared_cases": [],
    }
    if len(seed_cases) >= 2:
        left = seed_cases[0].summary
        right = seed_cases[1].summary
        fields = ("drag_coefficient", "downforce_coefficient", "objective", "efficiency_constraint")
        deltas = {
            field: _optional_abs_delta(left.get(field), right.get(field))
            for field in fields
        }
        comparable = all(value is not None for value in deltas.values())
        passed = comparable and all(
            value <= reproducibility_tolerance
            for value in deltas.values()
            if value is not None
        )
        reproducibility = {
            "status": "pass" if passed else "fail" if comparable else "not_executed",
            "tolerance": reproducibility_tolerance,
            "compared_cases": [str(seed_cases[0].case_dir), str(seed_cases[1].case_dir)],
            "absolute_deltas": deltas,
        }

    ok = all(status in {"prepared", "dry_run", "converged", "completed"} for status in statuses)
    if execute:
        ok = ok and all(status in {"converged", "completed"} for status in statuses)
    return {
        "schema_version": FIXED_GRID_PRIMAL_SCHEMA_VERSION,
        "kind": "fixed_grid_primal_suite_summary",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "ok": bool(ok),
        "execute": execute,
        "backend": backend,
        "docker_image": docker_image,
        "run_dir": str(run_dir),
        "topology_state_json": str(topology_state_json),
        "case_count": len(cases),
        "case_statuses": {
            case.case_dir.name: case.summary.get("status") for case in cases
        },
        "reproducibility": reproducibility,
        "cases": [
            {
                "name": case.case_dir.name,
                "case_dir": str(case.case_dir),
                "density_variant": case.summary.get("density_variant"),
                "status": case.summary.get("status"),
                "drag_coefficient": case.summary.get("drag_coefficient"),
                "downforce_coefficient": case.summary.get("downforce_coefficient"),
                "efficiency_constraint": case.summary.get("efficiency_constraint"),
                "summary_json": str(case.primal_summary_json),
            }
            for case in cases
        ],
    }


def _write_suite_history(path: Path, cases: list[FixedGridPrimalCaseArtifacts]) -> None:
    rows = []
    for case in cases:
        summary = case.summary
        density = dict(summary.get("density_input") or {})
        stats = dict(density.get("statistics") or {})
        rows.append(
            {
                "name": case.case_dir.name,
                "density_variant": summary.get("density_variant"),
                "status": summary.get("status"),
                "drag_coefficient": summary.get("drag_coefficient"),
                "downforce_coefficient": summary.get("downforce_coefficient"),
                "efficiency_constraint": summary.get("efficiency_constraint"),
                "density_mean": stats.get("mean"),
                "density_min": stats.get("min"),
                "density_max": stats.get("max"),
                "density_hash": density.get("hash_sha256_float32"),
                "case_dir": case.case_dir,
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _suite_markdown(summary: dict[str, object]) -> str:
    rows = "\n".join(
        "| {name} | {density_variant} | {status} | {drag} | {downforce} |".format(
            name=case["name"],
            density_variant=case["density_variant"],
            status=case["status"],
            drag=case["drag_coefficient"],
            downforce=case["downforce_coefficient"],
        )
        for case in summary["cases"]
    )
    return f"""# Fixed-Grid Primal Suite

| Field | Value |
| --- | --- |
| Roadmap phase | `T2` |
| OK | `{str(summary['ok']).lower()}` |
| Execute | `{str(summary['execute']).lower()}` |
| Backend | `{summary['backend']}` |
| Reproducibility | `{dict(summary['reproducibility'])['status']}` |

| Case | Density variant | Status | Drag | Downforce |
| --- | --- | --- | --- | --- |
{rows}
"""


def _optional_abs_delta(left: object, right: object) -> float | None:
    if left is None or right is None:
        return None
    return abs(float(left) - float(right))


def _array_stats(values: np.ndarray) -> dict[str, object]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(np.min(array)) if array.size else 0.0,
        "max": float(np.max(array)) if array.size else 0.0,
        "mean": float(np.mean(array)) if array.size else 0.0,
        "l2": float(np.linalg.norm(array)) if array.size else 0.0,
        "nonzero_count": int(np.count_nonzero(np.abs(array) > 1.0e-12)),
        "cell_count": int(array.size),
    }


def _array_hash(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    return hashlib.sha256(array.tobytes()).hexdigest()


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


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
