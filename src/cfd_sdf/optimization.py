from __future__ import annotations

import json
import random
import shutil
from csv import DictWriter
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from .candidate_constraints import ConstraintRecord, build_constraint_records, constraint_penalty
from .config import load_project
from .constraints import check_constraints
from .execution import run_openfoam_case
from .export_vtk import export_vti, export_zero_surface
from .openfoam import generate_openfoam_case
from .parametric import (
    OPTIMIZATION_VARIABLES,
    PARAMETER_BOUNDS,
    FrontWingParameters,
    clamp_parameters,
    default_parameters,
    mock_aero,
    parameters_from_dict,
    parameters_to_dict,
    write_parametric_front_wing_stl,
)
from .sdf import build_fields


@dataclass(frozen=True)
class CandidateResult:
    index: int
    candidate_dir: Path
    project_yaml: Path
    parameters: dict[str, float]
    status: str
    rejection_reasons: list[str]
    constraints_ok: bool
    constraint_records: list[ConstraintRecord]
    objective: float
    drag_coefficient: float
    downforce_coefficient: float
    front_downforce_coefficient: float
    rear_downforce_coefficient: float
    front_downforce_ratio: float
    efficiency: float
    efficiency_constraint: float
    penalty: float

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["candidate_dir"] = str(self.candidate_dir)
        data["project_yaml"] = str(self.project_yaml)
        data["constraint_records"] = [record.to_dict() for record in self.constraint_records]
        return data


@dataclass(frozen=True)
class OptimizationSummary:
    run_dir: Path
    evaluator: str
    iterations: int
    history_csv: Path
    best_candidate: CandidateResult
    candidates: list[CandidateResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "run_dir": str(self.run_dir),
            "evaluator": self.evaluator,
            "iterations": self.iterations,
            "history_csv": str(self.history_csv),
            "best_candidate": self.best_candidate.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def run_parametric_optimization(
    base_project_yaml: Path,
    *,
    run_dir: Path,
    iterations: int,
    evaluator: str = "mock",
    seed: int = 1,
    voxel_size_m: float | None = 0.08,
    backend: str = "auto",
    resume: bool = False,
    reject_before_cfd: bool = True,
) -> OptimizationSummary:
    if evaluator not in {"mock", "openfoam-dry-run"}:
        raise ValueError(f"Unsupported parametric evaluator: {evaluator}")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    rng = random.Random(seed)
    run_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[CandidateResult] = []

    default = default_parameters()
    parameter_sets = [default]
    for _ in range(iterations - 1):
        parameter_sets.append(_sample_parameters(rng))

    for index, params in enumerate(parameter_sets):
        candidate_dir = run_dir / f"candidate_{index:04d}"
        result_path = candidate_dir / "candidate_result.json"
        if resume and result_path.exists():
            result = _candidate_from_dict(json.loads(result_path.read_text(encoding="utf-8")))
            candidates.append(result)
            continue
        project_yaml = create_candidate_project(
            base_project_yaml,
            candidate_dir,
            params,
            voxel_size_m=voxel_size_m,
        )
        result = evaluate_candidate(
            project_yaml,
            params,
            index=index,
            candidate_dir=candidate_dir,
            evaluator=evaluator,
            backend=backend,
            reject_before_cfd=reject_before_cfd,
        )
        candidates.append(result)
        (candidate_dir / "candidate_result.json").write_text(
            json.dumps(result.to_dict(), indent=2),
            encoding="utf-8",
        )

    accepted = [candidate for candidate in candidates if candidate.status == "accepted"]
    best_pool = accepted or candidates
    best = min(best_pool, key=lambda item: item.objective)
    history_csv = run_dir / "history.csv"
    _write_history_csv(history_csv, candidates)
    summary = OptimizationSummary(
        run_dir=run_dir,
        evaluator=evaluator,
        iterations=iterations,
        history_csv=history_csv,
        best_candidate=best,
        candidates=candidates,
    )
    (run_dir / "optimization_summary.json").write_text(
        json.dumps(summary.to_dict(), indent=2),
        encoding="utf-8",
    )
    _write_best(run_dir, best)
    return summary


def create_candidate_project(
    base_project_yaml: Path,
    candidate_dir: Path,
    params: FrontWingParameters,
    *,
    voxel_size_m: float | None,
) -> Path:
    base_project_yaml = base_project_yaml.resolve()
    base_dir = base_project_yaml.parent
    candidate_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir = candidate_dir / "geometry"
    if geometry_dir.exists():
        shutil.rmtree(geometry_dir)
    shutil.copytree(base_dir / "geometry", geometry_dir)

    write_parametric_front_wing_stl(geometry_dir / "front_wing_initial.stl", params)
    project_data = yaml.safe_load(base_project_yaml.read_text(encoding="utf-8")) or {}
    project_data["output_dir"] = "runs/front_wing_demo"
    if voxel_size_m is not None:
        project_data.setdefault("grid", {})["voxel_size_m"] = float(voxel_size_m)

    project_yaml = candidate_dir / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(project_data, sort_keys=False), encoding="utf-8")
    (candidate_dir / "parameters.json").write_text(
        json.dumps(parameters_to_dict(params), indent=2),
        encoding="utf-8",
    )
    return project_yaml


def evaluate_candidate(
    project_yaml: Path,
    params: FrontWingParameters,
    *,
    index: int,
    candidate_dir: Path,
    evaluator: str,
    backend: str,
    reject_before_cfd: bool = True,
) -> CandidateResult:
    config = load_project(project_yaml)
    bundle = build_fields(config)
    report, derived = check_constraints(config, bundle)
    config.resolved_output_dir.mkdir(parents=True, exist_ok=True)
    (config.resolved_output_dir / "report.json").write_text(
        json.dumps(report.to_dict(), indent=2),
        encoding="utf-8",
    )
    export_vti(bundle, config.resolved_output_dir, derived)
    export_zero_surface(bundle, config.resolved_output_dir)

    aero = mock_aero(params, config.objective.efficiency_min, config.front_downforce_ratio.x_split_m)
    records = build_constraint_records(report.to_dict(), aero, config)
    enforced_failures = [record for record in records if record.enforced and not record.satisfied]
    rejection_reasons = [record.name for record in enforced_failures]
    status = "rejected" if rejection_reasons else "accepted"
    penalty = constraint_penalty(records)
    objective = -aero["downforce_coefficient"] + penalty

    should_prepare_cfd = evaluator == "openfoam-dry-run" and (status == "accepted" or not reject_before_cfd)
    if should_prepare_cfd:
        case_dir = config.resolved_output_dir / "openfoam_front_wing"
        summary = generate_openfoam_case(config, bundle, case_dir)
        (case_dir / "openfoam_case_summary.json").write_text(
            json.dumps(summary.to_dict(), indent=2),
            encoding="utf-8",
        )
        run_openfoam_case(case_dir, backend=backend, dry_run=True)

    return CandidateResult(
        index=index,
        candidate_dir=candidate_dir,
        project_yaml=project_yaml,
        parameters=parameters_to_dict(params),
        status=status,
        rejection_reasons=rejection_reasons,
        constraints_ok=status == "accepted",
        constraint_records=records,
        objective=float(objective),
        drag_coefficient=float(aero["drag_coefficient"]),
        downforce_coefficient=float(aero["downforce_coefficient"]),
        front_downforce_coefficient=float(aero["front_downforce_coefficient"]),
        rear_downforce_coefficient=float(aero["rear_downforce_coefficient"]),
        front_downforce_ratio=float(aero["front_downforce_ratio"]),
        efficiency=float(aero["efficiency"]),
        efficiency_constraint=float(aero["efficiency_constraint"]),
        penalty=float(penalty),
    )


def _sample_parameters(rng: random.Random) -> FrontWingParameters:
    values = parameters_to_dict(default_parameters())
    for key in OPTIMIZATION_VARIABLES:
        lower, upper = PARAMETER_BOUNDS[key]
        values[key] = rng.uniform(lower, upper)
    return clamp_parameters(parameters_from_dict(values))


def _write_history_csv(path: Path, candidates: list[CandidateResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        "candidate_dir",
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
                    "candidate_dir": candidate.candidate_dir,
                }
            )


def _candidate_from_dict(data: dict[str, object]) -> CandidateResult:
    return CandidateResult(
        index=int(data["index"]),
        candidate_dir=Path(str(data["candidate_dir"])),
        project_yaml=Path(str(data["project_yaml"])),
        parameters={key: float(value) for key, value in dict(data["parameters"]).items()},
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
        objective=float(data["objective"]),
        drag_coefficient=float(data["drag_coefficient"]),
        downforce_coefficient=float(data["downforce_coefficient"]),
        front_downforce_coefficient=float(data.get("front_downforce_coefficient", data["downforce_coefficient"])),
        rear_downforce_coefficient=float(data.get("rear_downforce_coefficient", 0.0)),
        front_downforce_ratio=float(data.get("front_downforce_ratio", 1.0)),
        efficiency=float(data["efficiency"]),
        efficiency_constraint=float(data["efficiency_constraint"]),
        penalty=float(data["penalty"]),
    )


def _write_best(run_dir: Path, best: CandidateResult) -> None:
    best_dir = run_dir / "best"
    if best_dir.exists():
        shutil.rmtree(best_dir)
    shutil.copytree(best.candidate_dir, best_dir)
