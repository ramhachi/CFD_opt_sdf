from __future__ import annotations

import json
import math
import shutil
from csv import DictWriter
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .adjoint import run_openfoam_adjoint_adapter
from .candidate_constraints import build_constraint_records, constraint_penalty
from .cfd import evaluate_openfoam_case
from .config import ProjectConfig, load_project
from .density_optimizer import (
    DensityOptimizerControls,
    DensityStepResult,
    run_density_update_step_from_sensitivity,
)
from .design_state import read_density_design_state, resolve_design_state_path
from .execution import run_openfoam_case
from .openfoam import generate_openfoam_case
from .projection import project_surface_sensitivity_to_density, write_mock_surface_sensitivity_csv
from .sdf import build_fields


@dataclass(frozen=True)
class PrimalCfdStepResult:
    case_dir: Path
    case_summary_json: Path
    run_summary_json: Path
    cfd_summary_json: Path | None
    run: dict[str, object]
    cfd_summary: dict[str, object] | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None and self.cfd_summary is not None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("case_dir", "case_summary_json", "run_summary_json", "cfd_summary_json"):
            if data[key] is not None:
                data[key] = str(data[key])
        data["ok"] = self.ok
        return data


@dataclass(frozen=True)
class AdjointTopologyStepResult:
    index: int
    step_dir: Path
    input_design_state_json: Path
    output_design_state_json: Path
    adjoint_summary_json: Path
    surface_sensitivity_csv: Path
    sensitivity_vti: Path
    sensitivity_summary_json: Path
    density_step_result_json: Path
    primal_case_dir: Path | None
    primal_run: dict[str, object] | None
    primal_cfd_summary: dict[str, object] | None
    primal_error: str | None
    post_update_primal_case_dir: Path | None
    post_update_primal_run: dict[str, object] | None
    post_update_primal_cfd_summary: dict[str, object] | None
    post_update_primal_error: str | None
    post_update_constraint_records: list[dict[str, object]] | None
    objective_source: str
    status: str
    objective: float
    constraints_ok: bool
    rejection_reasons: list[str]
    continuation_reason: str | None
    constraint_violation_before: float | None
    constraint_violation_after: float | None
    density_step: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "step_dir",
            "input_design_state_json",
            "output_design_state_json",
            "adjoint_summary_json",
            "surface_sensitivity_csv",
            "sensitivity_vti",
            "sensitivity_summary_json",
            "density_step_result_json",
            "primal_case_dir",
            "post_update_primal_case_dir",
        ):
            if data[key] is not None:
                data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class AdjointTopologySummary:
    run_dir: Path
    iterations: int
    accepted_count: int
    best_step: AdjointTopologyStepResult
    steps: list[AdjointTopologyStepResult]
    history_csv: Path
    summary_markdown: Path
    best_design_dir: Path
    stopped_reason: str | None = None
    stopped_step_index: int | None = None
    calibration_summary_json: Path | None = None
    calibration_record_json: Path | None = None
    sensitivity_update_multiplier: float = 1.0
    sensitivity_derivative_multiplier: float | None = None
    constraint_sensitivity_weight: float = 0.0
    sensitivity_calibration_status: str | None = None
    efficiency_min_override: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "run_dir": str(self.run_dir),
            "iterations": self.iterations,
            "completed_iterations": len(self.steps),
            "accepted_count": self.accepted_count,
            "best_step": self.best_step.to_dict(),
            "history_csv": str(self.history_csv),
            "summary_markdown": str(self.summary_markdown),
            "best_design_dir": str(self.best_design_dir),
            "stopped_reason": self.stopped_reason,
            "stopped_step_index": self.stopped_step_index,
            "calibration_summary_json": str(self.calibration_summary_json) if self.calibration_summary_json else None,
            "calibration_record_json": str(self.calibration_record_json) if self.calibration_record_json else None,
            "sensitivity_update_multiplier": self.sensitivity_update_multiplier,
            "sensitivity_derivative_multiplier": self.sensitivity_derivative_multiplier,
            "constraint_sensitivity_weight": self.constraint_sensitivity_weight,
            "sensitivity_calibration_status": self.sensitivity_calibration_status,
            "efficiency_min_override": self.efficiency_min_override,
            "steps": [step.to_dict() for step in self.steps],
        }


def run_adjoint_topology_optimization(
    initial_design_state_json: Path,
    *,
    run_dir: Path,
    iterations: int,
    backend: str = "auto",
    primal_execute: bool = False,
    adjoint_execute: bool = False,
    post_update_primal_execute: bool = False,
    primal_timeout_seconds: int | None = None,
    post_update_primal_timeout_seconds: int | None = None,
    timeout_seconds: int | None = None,
    density_controls: DensityOptimizerControls | None = None,
    resume: bool = False,
    stop_on_rejection: bool = False,
    continue_on_constraint_improvement: bool = False,
    calibration_summary_json: Path | None = None,
    sensitivity_update_multiplier: float | None = None,
    sensitivity_derivative_multiplier: float | None = None,
    efficiency_min_override: float | None = None,
) -> AdjointTopologySummary:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    _validate_efficiency_min_override(efficiency_min_override)
    density_controls = density_controls or DensityOptimizerControls()
    run_dir.mkdir(parents=True, exist_ok=True)
    density_controls, calibration_status, calibration_record = _apply_sensitivity_calibration(
        density_controls,
        calibration_summary_json=calibration_summary_json,
        sensitivity_update_multiplier=sensitivity_update_multiplier,
        sensitivity_derivative_multiplier=sensitivity_derivative_multiplier,
    )
    calibration_record_json = None
    if calibration_record:
        calibration_record_json = run_dir / "adjoint_topology_calibration.json"
        calibration_record_json.write_text(json.dumps(calibration_record, indent=2), encoding="utf-8")
    current_design_state = initial_design_state_json
    steps: list[AdjointTopologyStepResult] = []
    stopped_reason: str | None = None
    stopped_step_index: int | None = None

    for index in range(iterations):
        step_dir = run_dir / f"adjoint_step_{index:04d}"
        result_path = step_dir / "adjoint_topology_step_result.json"
        if resume and result_path.exists():
            step = _step_from_dict(json.loads(result_path.read_text(encoding="utf-8")))
            steps.append(step)
            if _should_stop_after_step(
                step,
                stop_on_rejection=stop_on_rejection,
                continue_on_constraint_improvement=continue_on_constraint_improvement,
            ):
                stopped_reason = _stopped_reason(step)
                stopped_step_index = step.index
                break
            current_design_state = step.output_design_state_json
            continue

        step = run_adjoint_topology_step(
            current_design_state,
            step_dir=step_dir,
            index=index,
            backend=backend,
            primal_execute=primal_execute,
            adjoint_execute=adjoint_execute,
            post_update_primal_execute=post_update_primal_execute,
            primal_timeout_seconds=primal_timeout_seconds,
            post_update_primal_timeout_seconds=post_update_primal_timeout_seconds,
            timeout_seconds=timeout_seconds,
            density_controls=density_controls,
            continue_on_constraint_improvement=continue_on_constraint_improvement,
            efficiency_min_override=efficiency_min_override,
        )
        result_path.write_text(json.dumps(step.to_dict(), indent=2), encoding="utf-8")
        steps.append(step)
        if _should_stop_after_step(
            step,
            stop_on_rejection=stop_on_rejection,
            continue_on_constraint_improvement=continue_on_constraint_improvement,
        ):
            stopped_reason = _stopped_reason(step)
            stopped_step_index = step.index
            break
        current_design_state = step.output_design_state_json

    history_csv = run_dir / "adjoint_topology_history.csv"
    _write_history(history_csv, steps)
    summary_markdown = run_dir / "adjoint_topology_summary.md"
    best = _select_best(steps)
    best_design_dir = run_dir / "best_design"
    _promote_best(best.step_dir, best_design_dir)
    summary = AdjointTopologySummary(
        run_dir=run_dir,
        iterations=iterations,
        accepted_count=sum(1 for step in steps if step.status == "accepted"),
        best_step=best,
        steps=steps,
        history_csv=history_csv,
        summary_markdown=summary_markdown,
        best_design_dir=best_design_dir,
        stopped_reason=stopped_reason,
        stopped_step_index=stopped_step_index,
        calibration_summary_json=calibration_summary_json.resolve() if calibration_summary_json else None,
        calibration_record_json=calibration_record_json,
        sensitivity_update_multiplier=float(density_controls.sensitivity_update_multiplier),
        sensitivity_derivative_multiplier=(
            float(density_controls.sensitivity_derivative_multiplier)
            if density_controls.sensitivity_derivative_multiplier is not None
            else None
        ),
        constraint_sensitivity_weight=float(density_controls.constraint_sensitivity_weight),
        sensitivity_calibration_status=calibration_status,
        efficiency_min_override=efficiency_min_override,
    )
    (run_dir / "adjoint_topology_summary.json").write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    summary_markdown.write_text(_summary_markdown(summary), encoding="utf-8")
    return summary


def run_adjoint_topology_step(
    input_design_state_json: Path,
    *,
    step_dir: Path,
    index: int,
    backend: str,
    primal_execute: bool,
    adjoint_execute: bool,
    post_update_primal_execute: bool,
    primal_timeout_seconds: int | None,
    post_update_primal_timeout_seconds: int | None,
    timeout_seconds: int | None,
    density_controls: DensityOptimizerControls,
    continue_on_constraint_improvement: bool = False,
    efficiency_min_override: float | None = None,
) -> AdjointTopologyStepResult:
    step_dir.mkdir(parents=True, exist_ok=True)
    primal = None
    if primal_execute:
        primal = run_primal_cfd_for_design_state(
            input_design_state_json,
            step_dir=step_dir / "primal",
            backend=backend,
            timeout_seconds=primal_timeout_seconds if primal_timeout_seconds is not None else timeout_seconds,
            efficiency_min_override=efficiency_min_override,
        )
        if not primal.ok:
            raise RuntimeError(f"Primal CFD execution failed; see {primal.run_summary_json}")

    adjoint = run_openfoam_adjoint_adapter(
        input_design_state_json,
        primal_case_dir=primal.case_dir if primal is not None else None,
        adjoint_case_dir=step_dir / "adjoint",
        solver_backend=backend,
        dry_run=not adjoint_execute,
        timeout_seconds=timeout_seconds,
        mock_fallback=False,
    )
    if adjoint_execute and not adjoint.ok:
        raise RuntimeError(f"Adjoint execution failed; see {adjoint.summary_path}")
    if adjoint.sensitivity_vti is not None and adjoint.sensitivity_summary_json is not None:
        surface_csv = adjoint.surface_sensitivity_csv or (step_dir / "adjoint" / "surface_sensitivity.csv")
        sensitivity_vti = adjoint.sensitivity_vti
        sensitivity_summary_json = adjoint.sensitivity_summary_json
    elif adjoint_execute:
        raise RuntimeError(f"Adjoint execution did not produce a projected sensitivity; see {adjoint.summary_path}")
    else:
        surface_csv = step_dir / "adjoint" / "surface_sensitivity.csv"
        write_mock_surface_sensitivity_csv(input_design_state_json, output_csv=surface_csv)
        projection = project_surface_sensitivity_to_density(
            input_design_state_json,
            surface_csv,
            output_dir=step_dir / "projection",
        )
        sensitivity_vti = projection.sensitivity_vti
        sensitivity_summary_json = projection.sensitivity_summary_json
    density_step = run_density_update_step_from_sensitivity(
        input_design_state_json,
        step_dir=step_dir / "density_update",
        index=index,
        controls=density_controls,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=sensitivity_summary_json,
    )
    density_step_result_json = density_step.step_dir / "density_step_result.json"
    density_step_result_json.write_text(json.dumps(density_step.to_dict(), indent=2), encoding="utf-8")
    post_update_primal = None
    final_status = density_step.status
    final_objective = density_step.objective
    final_constraints_ok = density_step.constraints_ok
    final_rejection_reasons = density_step.rejection_reasons
    continuation_reason = None
    constraint_violation_before = None
    constraint_violation_after = None
    post_update_constraint_records = None
    objective_source = "density_update_low_fidelity"
    if post_update_primal_execute:
        post_update_primal = run_primal_cfd_for_design_state(
            density_step.output_design_state_json,
            step_dir=step_dir / "post_update_primal",
            backend=backend,
            timeout_seconds=(
                post_update_primal_timeout_seconds
                if post_update_primal_timeout_seconds is not None
                else primal_timeout_seconds if primal_timeout_seconds is not None else timeout_seconds
            ),
            efficiency_min_override=efficiency_min_override,
        )
        if not post_update_primal.ok:
            raise RuntimeError(f"Post-update primal CFD execution failed; see {post_update_primal.run_summary_json}")
        reevaluated = _status_from_post_update_cfd(
            density_step,
            post_update_primal,
            initial_primal_cfd_summary=primal.cfd_summary if primal is not None else None,
            continue_on_constraint_improvement=continue_on_constraint_improvement,
            efficiency_min_override=efficiency_min_override,
        )
        final_status = str(reevaluated["status"])
        final_objective = float(reevaluated["objective"])
        final_constraints_ok = bool(reevaluated["constraints_ok"])
        final_rejection_reasons = [str(item) for item in reevaluated["rejection_reasons"]]
        continuation_reason = str(reevaluated["continuation_reason"]) if reevaluated.get("continuation_reason") else None
        constraint_violation_before = _optional_float(reevaluated.get("constraint_violation_before"))
        constraint_violation_after = _optional_float(reevaluated.get("constraint_violation_after"))
        post_update_constraint_records = [dict(item) for item in reevaluated["constraint_records"]]
        objective_source = "post_update_primal_cfd"
    return _from_density_step(
        index=index,
        step_dir=step_dir,
        input_design_state_json=input_design_state_json,
        adjoint_summary_json=adjoint.summary_path,
        surface_sensitivity_csv=surface_csv,
        primal=primal,
        post_update_primal=post_update_primal,
        post_update_constraint_records=post_update_constraint_records,
        objective_source=objective_source,
        final_status=final_status,
        final_objective=final_objective,
        final_constraints_ok=final_constraints_ok,
        final_rejection_reasons=final_rejection_reasons,
        continuation_reason=continuation_reason,
        constraint_violation_before=constraint_violation_before,
        constraint_violation_after=constraint_violation_after,
        density_step=density_step,
    )


def run_primal_cfd_for_design_state(
    design_state_json: Path,
    *,
    step_dir: Path,
    backend: str,
    timeout_seconds: int | None,
    efficiency_min_override: float | None = None,
) -> PrimalCfdStepResult:
    step_dir.mkdir(parents=True, exist_ok=True)
    design_state_json = design_state_json.resolve()
    design_state = read_density_design_state(design_state_json)
    source_project = resolve_design_state_path(
        design_state_json,
        design_state.source_project,
        local_fallback=Path("project.yaml"),
    )
    config = _with_efficiency_min_override(load_project(source_project), efficiency_min_override)
    bundle = build_fields(config)
    case_dir = step_dir / "openfoam_front_wing"
    case_summary = generate_openfoam_case(config, bundle, case_dir)
    case_summary_json = case_dir / "openfoam_case_summary.json"
    case_summary_json.write_text(json.dumps(case_summary.to_dict(), indent=2), encoding="utf-8")

    run_result = run_openfoam_case(
        case_dir,
        backend=backend,
        dry_run=False,
        timeout_seconds=timeout_seconds,
    )
    cfd_summary_json = None
    cfd_summary = None
    error = None
    if not run_result.ok:
        error = "openfoam_timeout" if run_result.timed_out else "openfoam_run_failed"
        if run_result.error:
            error = f"{error}: {run_result.error}"
    else:
        try:
            evaluation = evaluate_openfoam_case(case_dir, config.objective.efficiency_min)
            cfd_summary = evaluation.to_dict()
            cfd_summary_json = case_dir / "cfd_summary.json"
            cfd_summary_json.write_text(json.dumps(cfd_summary, indent=2), encoding="utf-8")
            if not evaluation.ok:
                error = "openfoam_postprocess_failed: missing Cd or downforce"
        except Exception as exc:
            error = f"openfoam_postprocess_failed: {exc}"

    return PrimalCfdStepResult(
        case_dir=case_dir,
        case_summary_json=case_summary_json,
        run_summary_json=run_result.summary_path,
        cfd_summary_json=cfd_summary_json,
        run=run_result.to_dict(),
        cfd_summary=cfd_summary,
        error=error,
    )


def _from_density_step(
    *,
    index: int,
    step_dir: Path,
    input_design_state_json: Path,
    adjoint_summary_json: Path,
    surface_sensitivity_csv: Path,
    primal: PrimalCfdStepResult | None,
    post_update_primal: PrimalCfdStepResult | None,
    post_update_constraint_records: list[dict[str, object]] | None,
    objective_source: str,
    final_status: str,
    final_objective: float,
    final_constraints_ok: bool,
    final_rejection_reasons: list[str],
    continuation_reason: str | None,
    constraint_violation_before: float | None,
    constraint_violation_after: float | None,
    density_step: DensityStepResult,
) -> AdjointTopologyStepResult:
    return AdjointTopologyStepResult(
        index=index,
        step_dir=step_dir,
        input_design_state_json=input_design_state_json,
        output_design_state_json=density_step.output_design_state_json,
        adjoint_summary_json=adjoint_summary_json,
        surface_sensitivity_csv=surface_sensitivity_csv,
        sensitivity_vti=density_step.sensitivity_vti,
        sensitivity_summary_json=density_step.sensitivity_summary_json,
        density_step_result_json=density_step.step_dir / "density_step_result.json",
        primal_case_dir=primal.case_dir if primal is not None else None,
        primal_run=primal.run if primal is not None else None,
        primal_cfd_summary=primal.cfd_summary if primal is not None else None,
        primal_error=primal.error if primal is not None else None,
        post_update_primal_case_dir=post_update_primal.case_dir if post_update_primal is not None else None,
        post_update_primal_run=post_update_primal.run if post_update_primal is not None else None,
        post_update_primal_cfd_summary=post_update_primal.cfd_summary if post_update_primal is not None else None,
        post_update_primal_error=post_update_primal.error if post_update_primal is not None else None,
        post_update_constraint_records=post_update_constraint_records,
        objective_source=objective_source,
        status=final_status,
        objective=final_objective,
        constraints_ok=final_constraints_ok,
        rejection_reasons=final_rejection_reasons,
        continuation_reason=continuation_reason,
        constraint_violation_before=constraint_violation_before,
        constraint_violation_after=constraint_violation_after,
        density_step=density_step.to_dict(),
    )


def _status_from_post_update_cfd(
    density_step: DensityStepResult,
    post_update_primal: PrimalCfdStepResult,
    *,
    initial_primal_cfd_summary: dict[str, object] | None = None,
    continue_on_constraint_improvement: bool = False,
    efficiency_min_override: float | None = None,
) -> dict[str, object]:
    if post_update_primal.cfd_summary is None:
        raise ValueError("Post-update primal result has no cfd_summary")
    config = _with_efficiency_min_override(load_project(density_step.project_yaml), efficiency_min_override)
    aero = _aero_from_cfd_summary(
        post_update_primal.cfd_summary,
        config,
        fallback_front_ratio=density_step.front_downforce_ratio,
    )
    records = build_constraint_records(density_step.report, aero, config)
    enforced_failures = [record for record in records if record.enforced and not record.satisfied]
    rejection_reasons = [record.name for record in enforced_failures]
    status = "rejected" if rejection_reasons else "accepted"
    constraint_violation_before = None
    constraint_violation_after = _enforced_constraint_violation(records)
    continuation_reason = None
    if status == "rejected" and continue_on_constraint_improvement and initial_primal_cfd_summary is not None:
        initial_aero = _aero_from_cfd_summary(
            initial_primal_cfd_summary,
            config,
            fallback_front_ratio=density_step.front_downforce_ratio,
        )
        initial_records = build_constraint_records(density_step.report, initial_aero, config)
        constraint_violation_before = _enforced_constraint_violation(initial_records)
        if (
            _non_aero_enforced_constraints_ok(records)
            and constraint_violation_after < constraint_violation_before - 1.0e-12
        ):
            status = "improving_infeasible"
            continuation_reason = (
                "enforced_constraint_violation_decreased:"
                f"{constraint_violation_before:.8g}->{constraint_violation_after:.8g}"
            )
    penalty = constraint_penalty(records)
    objective = -aero["downforce_coefficient"] + penalty
    return {
        "status": status,
        "objective": float(objective),
        "constraints_ok": status == "accepted",
        "rejection_reasons": rejection_reasons,
        "continuation_reason": continuation_reason,
        "constraint_violation_before": constraint_violation_before,
        "constraint_violation_after": constraint_violation_after,
        "constraint_records": [record.to_dict() for record in records],
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


def _should_stop_after_step(
    step: AdjointTopologyStepResult,
    *,
    stop_on_rejection: bool,
    continue_on_constraint_improvement: bool,
) -> bool:
    if not stop_on_rejection or step.status == "accepted":
        return False
    if continue_on_constraint_improvement and step.status == "improving_infeasible":
        return False
    return True


def _enforced_constraint_violation(records: list[object]) -> float:
    total = 0.0
    for record in records:
        enforced = bool(getattr(record, "enforced", False))
        satisfied = bool(getattr(record, "satisfied", False))
        if not enforced or satisfied:
            continue
        name = str(getattr(record, "name", ""))
        value = float(getattr(record, "value", 0.0))
        limit = float(getattr(record, "limit", 0.0))
        if name.endswith("_min"):
            total += max(0.0, limit - value)
        else:
            total += max(0.0, value - limit)
    return float(total)


def _non_aero_enforced_constraints_ok(records: list[object]) -> bool:
    for record in records:
        if not bool(getattr(record, "enforced", False)):
            continue
        if str(getattr(record, "category", "")) == "aero":
            continue
        if not bool(getattr(record, "satisfied", False)):
            return False
    return True


def _apply_sensitivity_calibration(
    controls: DensityOptimizerControls,
    *,
    calibration_summary_json: Path | None,
    sensitivity_update_multiplier: float | None,
    sensitivity_derivative_multiplier: float | None,
) -> tuple[DensityOptimizerControls, str | None, dict[str, object] | None]:
    update_multiplier = float(controls.sensitivity_update_multiplier)
    derivative_multiplier = controls.sensitivity_derivative_multiplier
    calibration_status: str | None = None
    calibration_record: dict[str, object] | None = None

    if calibration_summary_json is not None:
        calibration_summary_json = calibration_summary_json.resolve()
        data = json.loads(calibration_summary_json.read_text(encoding="utf-8"))
        if data.get("kind") != "adjoint_calibration_summary":
            raise ValueError(f"Expected adjoint_calibration_summary, got {data.get('kind')!r}")
        recommended_update = data.get("recommended_sensitivity_multiplier_for_gradient_descent")
        if recommended_update is None:
            raise ValueError(f"Calibration summary has no recommended update multiplier: {calibration_summary_json}")
        update_multiplier = float(recommended_update)
        derivative_multiplier = _optional_float(data.get("recommended_derivative_multiplier"))
        calibration_status = str(data.get("calibration_status", "unknown"))
        calibration_record = {
            "schema_version": 1,
            "kind": "adjoint_topology_sensitivity_calibration",
            "source_calibration_summary_json": str(calibration_summary_json),
            "source_calibration_status": calibration_status,
            "source_observation_count": int(data.get("observation_count", 0)),
            "source_objective_scale_ratio_median": data.get("objective_scale_ratio_median"),
            "source_constraint_scale_ratio_median": data.get("constraint_scale_ratio_median"),
            "recommended_sensitivity_multiplier_for_gradient_descent": update_multiplier,
            "recommended_derivative_multiplier": derivative_multiplier,
        }

    if sensitivity_update_multiplier is not None:
        update_multiplier = float(sensitivity_update_multiplier)
        calibration_record = calibration_record or {
            "schema_version": 1,
            "kind": "adjoint_topology_sensitivity_calibration",
            "source_calibration_summary_json": str(calibration_summary_json.resolve()) if calibration_summary_json else None,
        }
        calibration_record["override_sensitivity_update_multiplier"] = update_multiplier
    if sensitivity_derivative_multiplier is not None:
        derivative_multiplier = float(sensitivity_derivative_multiplier)
        calibration_record = calibration_record or {
            "schema_version": 1,
            "kind": "adjoint_topology_sensitivity_calibration",
            "source_calibration_summary_json": str(calibration_summary_json.resolve()) if calibration_summary_json else None,
        }
        calibration_record["override_sensitivity_derivative_multiplier"] = derivative_multiplier

    calibrated = replace(
        controls,
        sensitivity_update_multiplier=update_multiplier,
        sensitivity_derivative_multiplier=derivative_multiplier,
    )
    if calibration_record is not None:
        calibration_record["applied_sensitivity_update_multiplier"] = update_multiplier
        calibration_record["applied_sensitivity_derivative_multiplier"] = derivative_multiplier
    return calibrated, calibration_status, calibration_record


def _validate_efficiency_min_override(efficiency_min_override: float | None) -> None:
    if efficiency_min_override is None:
        return
    if not math.isfinite(float(efficiency_min_override)):
        raise ValueError("efficiency_min_override must be finite")
    if float(efficiency_min_override) < 0.0:
        raise ValueError("efficiency_min_override must be non-negative")


def _with_efficiency_min_override(config: ProjectConfig, efficiency_min_override: float | None) -> ProjectConfig:
    if efficiency_min_override is None:
        return config
    return replace(
        config,
        objective=replace(config.objective, efficiency_min=float(efficiency_min_override)),
    )


def _write_history(path: Path, steps: list[AdjointTopologyStepResult]) -> None:
    fieldnames = [
        "index",
        "status",
        "objective",
        "constraints_ok",
        "rejection_reasons",
        "step_dir",
        "input_design_state_json",
        "output_design_state_json",
        "sensitivity_vti",
        "primal_case_dir",
        "primal_error",
        "post_update_primal_case_dir",
        "post_update_primal_error",
        "objective_source",
        "continuation_reason",
        "constraint_violation_before",
        "constraint_violation_after",
        "sensitivity_update_multiplier",
        "sensitivity_derivative_multiplier",
        "constraint_sensitivity_weight",
        "density_step_result_json",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for step in steps:
            controls = dict(step.density_step.get("controls", {}))
            writer.writerow(
                {
                    "index": step.index,
                    "status": step.status,
                    "objective": step.objective,
                    "constraints_ok": step.constraints_ok,
                    "rejection_reasons": ";".join(step.rejection_reasons),
                    "step_dir": step.step_dir,
                    "input_design_state_json": step.input_design_state_json,
                    "output_design_state_json": step.output_design_state_json,
                    "sensitivity_vti": step.sensitivity_vti,
                    "primal_case_dir": step.primal_case_dir or "",
                    "primal_error": step.primal_error or "",
                    "post_update_primal_case_dir": step.post_update_primal_case_dir or "",
                    "post_update_primal_error": step.post_update_primal_error or "",
                    "objective_source": step.objective_source,
                    "continuation_reason": step.continuation_reason or "",
                    "constraint_violation_before": (
                        "" if step.constraint_violation_before is None else step.constraint_violation_before
                    ),
                    "constraint_violation_after": (
                        "" if step.constraint_violation_after is None else step.constraint_violation_after
                    ),
                    "sensitivity_update_multiplier": controls.get("sensitivity_update_multiplier", ""),
                    "sensitivity_derivative_multiplier": controls.get("sensitivity_derivative_multiplier", ""),
                    "constraint_sensitivity_weight": controls.get("constraint_sensitivity_weight", ""),
                    "density_step_result_json": step.density_step_result_json,
                }
            )


def _summary_markdown(summary: AdjointTopologySummary) -> str:
    rows = "\n".join(
        "| {index} | {status} | {objective:.8g} | {source} | {primal} | {post} | {constraints} | {violation} | {continuation} | `{step}` |".format(
            index=step.index,
            status=step.status,
            objective=step.objective,
            source=step.objective_source,
            primal="ok" if step.primal_cfd_summary else (step.primal_error or "not-run"),
            post="ok"
            if step.post_update_primal_cfd_summary
            else (step.post_update_primal_error or "not-run"),
            constraints=str(step.constraints_ok).lower(),
            violation=_violation_markdown(step),
            continuation=step.continuation_reason or "",
            step=step.step_dir,
        )
        for step in summary.steps
    )
    stopped_reason = summary.stopped_reason or "not-stopped"
    stopped_step = "" if summary.stopped_step_index is None else str(summary.stopped_step_index)
    derivative_multiplier = (
        ""
        if summary.sensitivity_derivative_multiplier is None
        else f"{summary.sensitivity_derivative_multiplier:.8g}"
    )
    efficiency_min_override = (
        ""
        if summary.efficiency_min_override is None
        else f"{summary.efficiency_min_override:.8g}"
    )
    return f"""# Adjoint Topology Run

| Field | Value |
| --- | --- |
| Iterations | {summary.iterations} |
| Completed iterations | {len(summary.steps)} |
| Accepted | {summary.accepted_count} |
| Stopped reason | {stopped_reason} |
| Stopped step | {stopped_step} |
| Sensitivity update multiplier | {summary.sensitivity_update_multiplier:.8g} |
| Sensitivity derivative multiplier | {derivative_multiplier} |
| Constraint sensitivity weight | {summary.constraint_sensitivity_weight:.8g} |
| Sensitivity calibration status | {summary.sensitivity_calibration_status or ""} |
| Efficiency min override | {efficiency_min_override} |
| Best objective | {summary.best_step.objective:.8g} |
| Best step | `{summary.best_step.step_dir}` |
| Best export | `{summary.best_design_dir}` |

## Steps

| Index | Status | Objective | Objective source | Primal CFD | Updated primal CFD | Constraints OK | Violation before->after | Continuation reason | Step |
| ---: | --- | ---: | --- | --- | --- | --- | --- | --- | --- |
{rows}
"""


def _violation_markdown(step: AdjointTopologyStepResult) -> str:
    if step.constraint_violation_before is None and step.constraint_violation_after is None:
        return ""
    before = "" if step.constraint_violation_before is None else f"{step.constraint_violation_before:.8g}"
    after = "" if step.constraint_violation_after is None else f"{step.constraint_violation_after:.8g}"
    return f"{before}->{after}"


def _select_best(steps: list[AdjointTopologyStepResult]) -> AdjointTopologyStepResult:
    accepted = [step for step in steps if step.status == "accepted"]
    return min(accepted or steps, key=lambda step: step.objective)


def _stopped_reason(step: AdjointTopologyStepResult) -> str:
    reasons = ",".join(step.rejection_reasons) if step.rejection_reasons else step.status
    return f"step_{step.index:04d}_{step.status}:{reasons}"


def _promote_best(step_dir: Path, best_design_dir: Path) -> None:
    if best_design_dir.exists():
        shutil.rmtree(best_design_dir)
    shutil.copytree(step_dir, best_design_dir)


def _step_from_dict(data: dict[str, object]) -> AdjointTopologyStepResult:
    return AdjointTopologyStepResult(
        index=int(data["index"]),
        step_dir=Path(str(data["step_dir"])),
        input_design_state_json=Path(str(data["input_design_state_json"])),
        output_design_state_json=Path(str(data["output_design_state_json"])),
        adjoint_summary_json=Path(str(data["adjoint_summary_json"])),
        surface_sensitivity_csv=Path(str(data["surface_sensitivity_csv"])),
        sensitivity_vti=Path(str(data["sensitivity_vti"])),
        sensitivity_summary_json=Path(str(data["sensitivity_summary_json"])),
        density_step_result_json=Path(str(data["density_step_result_json"])),
        primal_case_dir=Path(str(data["primal_case_dir"])) if data.get("primal_case_dir") else None,
        primal_run=dict(data["primal_run"]) if data.get("primal_run") else None,
        primal_cfd_summary=dict(data["primal_cfd_summary"]) if data.get("primal_cfd_summary") else None,
        primal_error=str(data["primal_error"]) if data.get("primal_error") else None,
        post_update_primal_case_dir=Path(str(data["post_update_primal_case_dir"])) if data.get("post_update_primal_case_dir") else None,
        post_update_primal_run=dict(data["post_update_primal_run"]) if data.get("post_update_primal_run") else None,
        post_update_primal_cfd_summary=dict(data["post_update_primal_cfd_summary"]) if data.get("post_update_primal_cfd_summary") else None,
        post_update_primal_error=str(data["post_update_primal_error"]) if data.get("post_update_primal_error") else None,
        post_update_constraint_records=[dict(item) for item in data.get("post_update_constraint_records", [])]
        if data.get("post_update_constraint_records")
        else None,
        objective_source=str(data.get("objective_source", "density_update_low_fidelity")),
        status=str(data["status"]),
        objective=float(data["objective"]),
        constraints_ok=bool(data["constraints_ok"]),
        rejection_reasons=[str(item) for item in data.get("rejection_reasons", [])],
        continuation_reason=str(data["continuation_reason"]) if data.get("continuation_reason") else None,
        constraint_violation_before=_optional_float(data.get("constraint_violation_before")),
        constraint_violation_after=_optional_float(data.get("constraint_violation_after")),
        density_step=dict(data["density_step"]),
    )
