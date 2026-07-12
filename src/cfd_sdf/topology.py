from __future__ import annotations

import json
import random
import shutil
from csv import DictWriter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pyvista as pv
import yaml

from .candidate_constraints import ConstraintRecord, build_constraint_records, constraint_penalty
from .config import ProjectConfig, load_project
from .constraints import check_constraints
from .cfd import evaluate_openfoam_case
from .design_state import create_density_design_state, write_density_design_state
from .execution import run_openfoam_case
from .export_vtk import export_vti, export_zero_surface
from .openfoam import generate_openfoam_case
from .sdf import FieldBundle, build_fields


@dataclass(frozen=True)
class TopologyControls:
    main_chord_cells: int = 12
    span_fraction: float = 0.86
    include_flap: bool = True
    include_endplates: bool = True
    include_center_vane: bool = False
    bridge_width_cells: int = 2

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TopologyCandidateResult:
    index: int
    candidate_dir: Path
    project_yaml: Path
    design_state_json: Path
    density_vti: Path
    density_stl: Path
    controls: dict[str, object]
    status: str
    rejection_reasons: list[str]
    constraints_ok: bool
    constraint_records: list[ConstraintRecord]
    report: dict[str, object]
    objective: float
    penalty: float
    drag_coefficient: float
    downforce_coefficient: float
    front_downforce_coefficient: float
    rear_downforce_coefficient: float
    front_downforce_ratio: float
    efficiency: float
    efficiency_constraint: float
    solid_fraction: float
    density_cell_count: int
    cfd_case_dir: Path | None
    cfd_run: dict[str, object] | None
    cfd_summary: dict[str, object] | None
    cfd_error: str | None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("candidate_dir", "project_yaml", "design_state_json", "density_vti", "density_stl"):
            data[key] = str(data[key])
        if self.cfd_case_dir is not None:
            data["cfd_case_dir"] = str(self.cfd_case_dir)
        data["constraint_records"] = [record.to_dict() for record in self.constraint_records]
        return data


@dataclass(frozen=True)
class TopologyExplorationSummary:
    run_dir: Path
    evaluator: str
    iterations: int
    accepted_count: int
    best_candidate: TopologyCandidateResult
    candidates: list[TopologyCandidateResult]
    history_csv: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "run_dir": str(self.run_dir),
            "evaluator": self.evaluator,
            "iterations": self.iterations,
            "accepted_count": self.accepted_count,
            "best_candidate": self.best_candidate.to_dict(),
            "history_csv": str(self.history_csv),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def run_topology_exploration(
    base_project_yaml: Path,
    *,
    run_dir: Path,
    iterations: int,
    seed: int = 1,
    voxel_size_m: float | None = 0.08,
    evaluator: str = "low-fi",
    backend: str = "auto",
    timeout_seconds: int | None = None,
    resume: bool = False,
    reject_before_cfd: bool = True,
) -> TopologyExplorationSummary:
    if evaluator not in {"low-fi", "openfoam-dry-run", "openfoam"}:
        raise ValueError(f"Unsupported topology evaluator: {evaluator}")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    run_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    candidates: list[TopologyCandidateResult] = []

    controls = [TopologyControls()]
    for _ in range(iterations - 1):
        controls.append(_sample_controls(rng))

    for index, control in enumerate(controls):
        candidate_dir = run_dir / f"topology_{index:04d}"
        result_path = candidate_dir / "topology_result.json"
        if resume and result_path.exists():
            candidates.append(_result_from_dict(json.loads(result_path.read_text(encoding="utf-8"))))
            continue
        result = evaluate_topology_candidate(
            base_project_yaml,
            candidate_dir=candidate_dir,
            index=index,
            controls=control,
            voxel_size_m=voxel_size_m,
            evaluator=evaluator,
            backend=backend,
            timeout_seconds=timeout_seconds,
            reject_before_cfd=reject_before_cfd,
        )
        candidates.append(result)
        result_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    history_csv = run_dir / "topology_history.csv"
    _write_history(history_csv, candidates)
    best = _select_best(candidates)
    summary = TopologyExplorationSummary(
        run_dir=run_dir,
        evaluator=evaluator,
        iterations=iterations,
        accepted_count=sum(1 for candidate in candidates if candidate.status == "accepted"),
        best_candidate=best,
        candidates=candidates,
        history_csv=history_csv,
    )
    (run_dir / "topology_summary.json").write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    _promote_best(run_dir, best)
    return summary


def evaluate_topology_candidate(
    base_project_yaml: Path,
    *,
    candidate_dir: Path,
    index: int,
    controls: TopologyControls,
    voxel_size_m: float | None,
    evaluator: str = "low-fi",
    backend: str = "auto",
    timeout_seconds: int | None = None,
    reject_before_cfd: bool = True,
) -> TopologyCandidateResult:
    project_yaml = _create_topology_project(base_project_yaml, candidate_dir, voxel_size_m=voxel_size_m)
    config = load_project(project_yaml)

    base_bundle = build_fields(config)
    density = build_density_field(base_bundle, controls)
    density_vti = candidate_dir / "density.vti"
    legacy_density_vti = candidate_dir / "density_field.vti"
    density_stl = candidate_dir / "geometry" / "front_wing_initial.stl"
    export_density_vti(base_bundle, density, density_vti)
    export_density_vti(base_bundle, density, legacy_density_vti)
    export_density_stl(base_bundle, density, density_stl)
    design_state_json = candidate_dir / "design_state.json"
    design_state = create_density_design_state(
        bundle=base_bundle,
        density=density,
        density_vti=density_vti,
        derived_geometry=density_stl,
        source_project=project_yaml,
    )
    write_density_design_state(design_state, design_state_json)

    config = load_project(project_yaml)
    bundle = build_fields(config)
    report, derived = check_constraints(config, bundle)
    config.resolved_output_dir.mkdir(parents=True, exist_ok=True)
    (config.resolved_output_dir / "report.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    export_vti(bundle, config.resolved_output_dir, derived)
    export_zero_surface(bundle, config.resolved_output_dir)

    density_cell_count = int((density >= 0.5).sum())
    allowed_count = int((base_bundle.arrays["allowed_phi"] <= 0.0).sum())
    solid_fraction = density_cell_count / allowed_count if allowed_count else 0.0
    aero = low_fidelity_topology_aero(density, base_bundle, config, controls)
    records = build_constraint_records(report.to_dict(), aero, config)
    enforced_failures = [record for record in records if record.enforced and not record.satisfied]
    rejection_reasons = [record.name for record in enforced_failures]
    status = "rejected" if rejection_reasons else "accepted"
    penalty = constraint_penalty(records)
    objective = -aero["downforce_coefficient"] + penalty
    cfd_case_dir: Path | None = None
    cfd_run: dict[str, object] | None = None
    cfd_summary: dict[str, object] | None = None
    cfd_error: str | None = None

    should_prepare_cfd = evaluator in {"openfoam-dry-run", "openfoam"} and (status == "accepted" or not reject_before_cfd)
    if should_prepare_cfd:
        case_dir = config.resolved_output_dir / "openfoam_front_wing"
        cfd_case_dir = case_dir
        summary = generate_openfoam_case(config, bundle, case_dir)
        (case_dir / "openfoam_case_summary.json").write_text(
            json.dumps(summary.to_dict(), indent=2),
            encoding="utf-8",
        )
        run_result = run_openfoam_case(
            case_dir,
            backend=backend,
            dry_run=evaluator == "openfoam-dry-run",
            timeout_seconds=timeout_seconds,
        )
        cfd_run = run_result.to_dict()
        if evaluator == "openfoam":
            if not run_result.ok:
                status = "failed"
                cfd_error = "openfoam_timeout" if run_result.timed_out else "openfoam_run_failed"
                if run_result.error:
                    cfd_error = f"{cfd_error}: {run_result.error}"
                rejection_reasons = [cfd_error]
                penalty = 1.0e6
                objective = 1.0e6
            else:
                try:
                    evaluation = evaluate_openfoam_case(case_dir, config.objective.efficiency_min)
                    cfd_summary = evaluation.to_dict()
                    (case_dir / "cfd_summary.json").write_text(json.dumps(cfd_summary, indent=2), encoding="utf-8")
                    if not evaluation.ok:
                        raise ValueError("OpenFOAM force coefficient postprocess did not produce Cd and downforce.")
                    aero = _aero_from_cfd_summary(cfd_summary, config, fallback_front_ratio=aero["front_downforce_ratio"])
                    records = build_constraint_records(report.to_dict(), aero, config)
                    enforced_failures = [record for record in records if record.enforced and not record.satisfied]
                    rejection_reasons = [record.name for record in enforced_failures]
                    status = "rejected" if rejection_reasons else "accepted"
                    penalty = constraint_penalty(records)
                    objective = -aero["downforce_coefficient"] + penalty
                except Exception as exc:
                    status = "failed"
                    cfd_error = f"openfoam_postprocess_failed: {exc}"
                    rejection_reasons = [cfd_error]
                    penalty = 1.0e6
                    objective = 1.0e6

    return TopologyCandidateResult(
        index=index,
        candidate_dir=candidate_dir,
        project_yaml=project_yaml,
        design_state_json=design_state_json,
        density_vti=density_vti,
        density_stl=density_stl,
        controls=controls.to_dict(),
        status=status,
        rejection_reasons=rejection_reasons,
        constraints_ok=status == "accepted",
        constraint_records=records,
        report=report.to_dict(),
        objective=float(objective),
        penalty=float(penalty),
        drag_coefficient=float(aero["drag_coefficient"]),
        downforce_coefficient=float(aero["downforce_coefficient"]),
        front_downforce_coefficient=float(aero["front_downforce_coefficient"]),
        rear_downforce_coefficient=float(aero["rear_downforce_coefficient"]),
        front_downforce_ratio=float(aero["front_downforce_ratio"]),
        efficiency=float(aero["efficiency"]),
        efficiency_constraint=float(aero["efficiency_constraint"]),
        solid_fraction=float(solid_fraction),
        density_cell_count=density_cell_count,
        cfd_case_dir=cfd_case_dir,
        cfd_run=cfd_run,
        cfd_summary=cfd_summary,
        cfd_error=cfd_error,
    )


def low_fidelity_topology_aero(
    density: np.ndarray,
    bundle: FieldBundle,
    config: ProjectConfig,
    controls: TopologyControls,
) -> dict[str, float]:
    solid = density >= 0.5
    spacing = float(bundle.grid.spacing)
    solid_count = int(solid.sum())
    if solid_count == 0:
        drag = 0.055
        downforce = 0.0
        return {
            "drag_coefficient": drag,
            "downforce_coefficient": downforce,
            "front_downforce_coefficient": 0.0,
            "rear_downforce_coefficient": 0.0,
            "front_downforce_ratio": 0.0,
            "efficiency": 0.0,
            "efficiency_constraint": float(config.objective.efficiency_min * drag),
        }

    allowed_count = int((bundle.arrays["allowed_phi"] <= 0.0).sum())
    solid_fraction = solid_count / allowed_count if allowed_count else 0.0
    planform_area = float(solid.any(axis=2).sum() * spacing * spacing)
    frontal_area = float(solid.any(axis=0).sum() * spacing * spacing)
    wetted_proxy_area = float(solid_count * spacing * spacing)

    ys = bundle.grid.axis(1)
    occupied_y = solid.any(axis=(0, 2))
    span_width = float(ys[occupied_y].max() - ys[occupied_y].min() + spacing) if occupied_y.any() else 0.0

    feature_gain = 1.0
    if controls.include_flap:
        feature_gain += 0.18
    if controls.include_endplates:
        feature_gain += 0.12
    if controls.include_center_vane:
        feature_gain += 0.06

    downforce = (0.36 * planform_area + 0.08 * span_width) * feature_gain
    drag = 0.055 + 0.06 * frontal_area + 0.018 * wetted_proxy_area + 0.025 * solid_fraction
    if controls.include_endplates:
        drag += 0.015
    if controls.include_center_vane:
        drag += 0.010

    xs = bundle.grid.axis(0)
    x_weights = solid.sum(axis=(1, 2)).astype(float)
    total_weight = float(x_weights.sum())
    front_weight = float(x_weights[xs >= config.front_downforce_ratio.x_split_m].sum())
    front_ratio = front_weight / total_weight if total_weight > 1.0e-12 else 0.0
    front_downforce = downforce * front_ratio
    rear_downforce = downforce - front_downforce
    efficiency = downforce / drag if abs(drag) > 1.0e-12 else 0.0

    return {
        "drag_coefficient": float(drag),
        "downforce_coefficient": float(downforce),
        "front_downforce_coefficient": float(front_downforce),
        "rear_downforce_coefficient": float(rear_downforce),
        "front_downforce_ratio": float(front_ratio),
        "efficiency": float(efficiency),
        "efficiency_constraint": float(config.objective.efficiency_min * drag - downforce),
    }


def _aero_from_cfd_summary(
    cfd_summary: dict[str, object],
    config: ProjectConfig,
    *,
    fallback_front_ratio: float,
) -> dict[str, float]:
    drag = float(cfd_summary["drag_coefficient"])
    downforce = float(cfd_summary["downforce_coefficient"])
    latest = dict(cfd_summary.get("latest", {}))
    front_lift = _optional_float(latest.get("Cl(f)", latest.get("Clf")))
    rear_lift = _optional_float(latest.get("Cl(r)", latest.get("Clr")))
    if front_lift is not None and rear_lift is not None:
        front_downforce = -front_lift
        rear_downforce = -rear_lift
    else:
        front_downforce = downforce * fallback_front_ratio
        rear_downforce = downforce - front_downforce
    front_ratio = front_downforce / downforce if abs(downforce) > 1.0e-12 else 0.0
    efficiency = cfd_summary.get("efficiency")
    efficiency_constraint = cfd_summary.get("efficiency_constraint")
    if efficiency is None:
        efficiency = downforce / drag if abs(drag) > 1.0e-12 else 0.0
    if efficiency_constraint is None:
        efficiency_constraint = config.objective.efficiency_min * drag - downforce
    return {
        "drag_coefficient": drag,
        "downforce_coefficient": downforce,
        "front_downforce_coefficient": float(front_downforce),
        "rear_downforce_coefficient": float(rear_downforce),
        "front_downforce_ratio": float(front_ratio),
        "efficiency": float(efficiency),
        "efficiency_constraint": float(efficiency_constraint),
    }


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def build_density_field(bundle: FieldBundle, controls: TopologyControls) -> np.ndarray:
    if "allowed_phi" not in bundle.arrays:
        raise ValueError("Topology density generation requires allowed_phi.")
    shape = bundle.grid.shape
    xs = bundle.grid.axis(0)
    ys = bundle.grid.axis(1)
    zs = bundle.grid.axis(2)
    x, y, z = np.meshgrid(xs, ys, zs, indexing="ij")

    allowed = bundle.arrays["allowed_phi"] <= 0.0
    forbidden_clear = bundle.arrays.get("forbidden_phi", np.ones(shape, dtype=np.float32)) > 0.0
    density = np.zeros(shape, dtype=np.float32)

    allowed_coords = np.argwhere(allowed)
    if allowed_coords.size == 0:
        raise ValueError("Allowed region contains no grid points.")
    mins = allowed_coords.min(axis=0)
    maxs = allowed_coords.max(axis=0)
    lo = bundle.grid.origin + mins * bundle.grid.spacing
    hi = bundle.grid.origin + maxs * bundle.grid.spacing
    center = 0.5 * (lo + hi)
    extent = hi - lo

    span = max(0.2, extent[1] * controls.span_fraction)
    main_chord = max(0.18, controls.main_chord_cells * bundle.grid.spacing)
    main_thick = max(0.04, 1.4 * bundle.grid.spacing)
    bridge_width = max(0.05, controls.bridge_width_cells * bundle.grid.spacing)

    _add_box(density, x, y, z, (center[0] + 0.08, center[1], center[2] - 0.03), (main_chord, span, main_thick))
    if controls.include_flap:
        _add_box(
            density,
            x,
            y,
            z,
            (center[0] - 0.12, center[1], center[2] + 0.08),
            (0.55 * main_chord, 0.92 * span, main_thick),
        )
        _add_box(
            density,
            x,
            y,
            z,
            (center[0] - 0.04, 0.35 * span, center[2] + 0.02),
            (bridge_width, bridge_width, 0.16),
        )
        _add_box(
            density,
            x,
            y,
            z,
            (center[0] - 0.04, -0.35 * span, center[2] + 0.02),
            (bridge_width, bridge_width, 0.16),
        )
    if controls.include_endplates:
        _add_box(density, x, y, z, (center[0], 0.50 * span, center[2] + 0.04), (0.55 * main_chord, bridge_width, 0.25))
        _add_box(density, x, y, z, (center[0], -0.50 * span, center[2] + 0.04), (0.55 * main_chord, bridge_width, 0.25))
    if controls.include_center_vane:
        _add_box(density, x, y, z, (center[0] + 0.02, center[1], center[2] + 0.10), (0.12, bridge_width, 0.22))

    # Always add mount/root bridges so geometry-only topology candidates have a chance to satisfy root connectivity.
    _add_box(density, x, y, z, (0.58, 0.32, 0.24), (0.20, 0.10, 0.15))
    _add_box(density, x, y, z, (0.58, -0.32, 0.24), (0.20, 0.10, 0.15))
    _add_box(density, x, y, z, (0.69, 0.32, 0.21), (0.25, 0.08, 0.08))
    _add_box(density, x, y, z, (0.69, -0.32, 0.21), (0.25, 0.08, 0.08))

    density *= allowed.astype(np.float32)
    density *= forbidden_clear.astype(np.float32)
    return density


def export_density_vti(bundle: FieldBundle, density: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    grid = pv.ImageData()
    grid.dimensions = bundle.grid.shape
    grid.origin = tuple(bundle.grid.origin.tolist())
    grid.spacing = (bundle.grid.spacing, bundle.grid.spacing, bundle.grid.spacing)
    grid.point_data["density"] = np.ascontiguousarray(density.ravel(order="F"))
    grid.point_data["allowed_mask"] = np.ascontiguousarray((bundle.arrays["allowed_phi"] <= 0.0).astype(np.uint8).ravel(order="F"))
    grid.save(path)
    return path


def export_density_stl(bundle: FieldBundle, density: np.ndarray, path: Path, iso_value: float = 0.5) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    grid = pv.ImageData()
    grid.dimensions = bundle.grid.shape
    grid.origin = tuple(bundle.grid.origin.tolist())
    grid.spacing = (bundle.grid.spacing, bundle.grid.spacing, bundle.grid.spacing)
    grid.point_data["density"] = np.ascontiguousarray(density.ravel(order="F"))
    surface = grid.contour(isosurfaces=[iso_value], scalars="density").triangulate()
    if surface.n_points == 0:
        raise ValueError("Density field produced an empty iso-surface.")
    surface.save(path)
    return path


def _add_box(
    density: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    center: tuple[float, float, float],
    extents: tuple[float, float, float],
) -> None:
    cx, cy, cz = center
    ex, ey, ez = (0.5 * value for value in extents)
    inside = (np.abs(x - cx) <= ex) & (np.abs(y - cy) <= ey) & (np.abs(z - cz) <= ez)
    density[inside] = 1.0


def _sample_controls(rng: random.Random) -> TopologyControls:
    return TopologyControls(
        main_chord_cells=rng.randint(8, 15),
        span_fraction=rng.uniform(0.72, 0.95),
        include_flap=rng.random() > 0.15,
        include_endplates=rng.random() > 0.20,
        include_center_vane=rng.random() > 0.55,
        bridge_width_cells=rng.randint(2, 3),
    )


def _create_topology_project(base_project_yaml: Path, candidate_dir: Path, *, voxel_size_m: float | None) -> Path:
    base_project_yaml = base_project_yaml.resolve()
    base_dir = base_project_yaml.parent
    candidate_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir = candidate_dir / "geometry"
    if geometry_dir.exists():
        shutil.rmtree(geometry_dir)
    shutil.copytree(base_dir / "geometry", geometry_dir)

    project_data = yaml.safe_load(base_project_yaml.read_text(encoding="utf-8")) or {}
    project_data["output_dir"] = "runs/front_wing_demo"
    if voxel_size_m is not None:
        project_data.setdefault("grid", {})["voxel_size_m"] = float(voxel_size_m)
    project_yaml = candidate_dir / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(project_data, sort_keys=False), encoding="utf-8")
    return project_yaml


def _write_history(path: Path, candidates: list[TopologyCandidateResult]) -> None:
    fieldnames = [
        "index",
        "status",
        "objective",
        "penalty",
        "constraints_ok",
        "rejection_reasons",
        "drag_coefficient",
        "downforce_coefficient",
        "front_downforce_coefficient",
        "rear_downforce_coefficient",
        "front_downforce_ratio",
        "efficiency",
        "efficiency_constraint",
        "solid_fraction",
        "density_cell_count",
        "candidate_dir",
        "design_state_json",
        "density_stl",
        "cfd_case_dir",
        "cfd_error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "index": candidate.index,
                    "status": candidate.status,
                    "objective": candidate.objective,
                    "penalty": candidate.penalty,
                    "constraints_ok": candidate.constraints_ok,
                    "rejection_reasons": ";".join(candidate.rejection_reasons),
                    "drag_coefficient": candidate.drag_coefficient,
                    "downforce_coefficient": candidate.downforce_coefficient,
                    "front_downforce_coefficient": candidate.front_downforce_coefficient,
                    "rear_downforce_coefficient": candidate.rear_downforce_coefficient,
                    "front_downforce_ratio": candidate.front_downforce_ratio,
                    "efficiency": candidate.efficiency,
                    "efficiency_constraint": candidate.efficiency_constraint,
                    "solid_fraction": candidate.solid_fraction,
                    "density_cell_count": candidate.density_cell_count,
                    "candidate_dir": candidate.candidate_dir,
                    "design_state_json": candidate.design_state_json,
                    "density_stl": candidate.density_stl,
                    "cfd_case_dir": candidate.cfd_case_dir or "",
                    "cfd_error": candidate.cfd_error or "",
                }
            )


def _select_best(candidates: list[TopologyCandidateResult]) -> TopologyCandidateResult:
    accepted = [candidate for candidate in candidates if candidate.status == "accepted"]
    best_pool = accepted or candidates
    return min(best_pool, key=lambda candidate: candidate.objective)


def _promote_best(run_dir: Path, best: TopologyCandidateResult) -> None:
    best_dir = run_dir / "best_topology"
    if best_dir.exists():
        shutil.rmtree(best_dir)
    shutil.copytree(best.candidate_dir, best_dir)


def _result_from_dict(data: dict[str, object]) -> TopologyCandidateResult:
    return TopologyCandidateResult(
        index=int(data["index"]),
        candidate_dir=Path(str(data["candidate_dir"])),
        project_yaml=Path(str(data["project_yaml"])),
        design_state_json=Path(str(data.get("design_state_json", Path(str(data["candidate_dir"])) / "design_state.json"))),
        density_vti=Path(str(data["density_vti"])),
        density_stl=Path(str(data["density_stl"])),
        controls=dict(data["controls"]),
        status=str(data.get("status", "accepted" if data.get("constraints_ok", False) else "rejected")),
        rejection_reasons=[str(item) for item in data.get("rejection_reasons", [])],
        constraints_ok=bool(data["constraints_ok"]),
        constraint_records=[
            ConstraintRecord(
                name=str(item["name"]),
                value=float(item["value"]),
                limit=float(item["limit"]),
                satisfied=bool(item["satisfied"]),
                enforced=bool(item["enforced"]),
                category=str(item["category"]),
                message=str(item["message"]),
            )
            for item in data.get("constraint_records", [])
        ],
        report=dict(data["report"]),
        objective=float(data.get("objective", data.get("solid_fraction", 0.0))),
        penalty=float(data.get("penalty", 0.0)),
        drag_coefficient=float(data.get("drag_coefficient", 0.0)),
        downforce_coefficient=float(data.get("downforce_coefficient", 0.0)),
        front_downforce_coefficient=float(data.get("front_downforce_coefficient", 0.0)),
        rear_downforce_coefficient=float(data.get("rear_downforce_coefficient", 0.0)),
        front_downforce_ratio=float(data.get("front_downforce_ratio", 0.0)),
        efficiency=float(data.get("efficiency", 0.0)),
        efficiency_constraint=float(data.get("efficiency_constraint", 0.0)),
        solid_fraction=float(data["solid_fraction"]),
        density_cell_count=int(data["density_cell_count"]),
        cfd_case_dir=Path(str(data["cfd_case_dir"])) if data.get("cfd_case_dir") else None,
        cfd_run=dict(data["cfd_run"]) if data.get("cfd_run") else None,
        cfd_summary=dict(data["cfd_summary"]) if data.get("cfd_summary") else None,
        cfd_error=str(data["cfd_error"]) if data.get("cfd_error") else None,
    )
