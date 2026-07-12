from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .adjoint_topology import run_primal_cfd_for_design_state
from .config import load_project
from .design_state import create_density_design_state, write_density_design_state
from .sdf import build_fields
from .sensitivity import read_density_update_vti, read_sensitivity_vti, write_vti_scalar_arrays
from .topology import export_density_stl, export_density_vti


ADJOINT_DIRECTION_CHECK_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DirectionMetric:
    name: str
    predicted_delta: float
    actual_delta: float
    sign_match: bool | None
    scale_ratio: float | None
    classification: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AdjointDirectionCheckSummary:
    step_result_json: Path
    output_dir: Path
    report_json: Path
    report_markdown: Path
    diagnostics_vti: Path
    density_update_vti: Path
    sensitivity_vti: Path
    objective_metric: DirectionMetric
    constraint_metric: DirectionMetric | None
    active_cell_count: int
    density_delta_l2: float
    density_delta_min: float
    density_delta_max: float
    initial_downforce_coefficient: float
    updated_downforce_coefficient: float
    initial_efficiency_constraint: float | None
    updated_efficiency_constraint: float | None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("step_result_json", "output_dir", "report_json", "report_markdown", "diagnostics_vti", "density_update_vti", "sensitivity_vti"):
            data[key] = str(data[key])
        data["objective_metric"] = self.objective_metric.to_dict()
        data["constraint_metric"] = self.constraint_metric.to_dict() if self.constraint_metric is not None else None
        data["schema_version"] = ADJOINT_DIRECTION_CHECK_SCHEMA_VERSION
        return data


@dataclass(frozen=True)
class PairedDirectionCandidate:
    name: str
    density_delta_multiplier: float
    direction_dir: Path
    design_state_json: Path
    density_update_vti: Path
    density_vti: Path
    density_stl: Path
    density_delta_l2: float
    density_delta_min: float
    density_delta_max: float
    predicted_objective_delta: float
    predicted_constraint_delta: float | None
    cfd_source: str
    primal_case_dir: Path | None
    primal_run: dict[str, object] | None
    primal_cfd_summary: dict[str, object] | None
    primal_error: str | None
    actual_objective_delta: float | None
    actual_constraint_delta: float | None
    objective_classification: str
    constraint_classification: str | None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("direction_dir", "design_state_json", "density_update_vti", "density_vti", "density_stl", "primal_case_dir"):
            if data[key] is not None:
                data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class PairedAdjointDirectionCheckSummary:
    step_result_json: Path
    output_dir: Path
    report_json: Path
    report_markdown: Path
    perturbation_mode: str
    perturbation_scale: float
    baseline_design_state_json: Path | None
    baseline_density_vti: Path | None
    baseline_density_stl: Path | None
    baseline_primal_case_dir: Path | None
    baseline_primal_run: dict[str, object] | None
    baseline_primal_cfd_summary: dict[str, object] | None
    baseline_primal_error: str | None
    initial_downforce_coefficient: float
    initial_efficiency_constraint: float | None
    active_cell_count: int
    density_delta_l2: float
    execute_primal: bool
    backend: str
    candidates: list[PairedDirectionCandidate]
    recommended_direction: str | None
    recommended_density_delta_multiplier: float | None
    suggested_sensitivity_multiplier_for_gradient_descent: float | None
    sensitivity_sign_decision: str

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "step_result_json",
            "output_dir",
            "report_json",
            "report_markdown",
            "baseline_design_state_json",
            "baseline_density_vti",
            "baseline_density_stl",
            "baseline_primal_case_dir",
        ):
            if data[key] is not None:
                data[key] = str(data[key])
        data["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        data["schema_version"] = ADJOINT_DIRECTION_CHECK_SCHEMA_VERSION
        data["kind"] = "paired_adjoint_direction_check"
        return data


@dataclass(frozen=True)
class CalibrationObservation:
    paired_report_json: Path
    perturbation_mode: str
    perturbation_scale: float
    direction: str
    density_delta_l2: float
    predicted_objective_delta: float
    actual_objective_delta: float
    objective_scale_ratio: float
    predicted_constraint_delta: float | None
    actual_constraint_delta: float | None
    constraint_scale_ratio: float | None
    objective_classification: str
    constraint_classification: str | None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["paired_report_json"] = str(self.paired_report_json)
        return data


@dataclass(frozen=True)
class AdjointCalibrationSummary:
    output_dir: Path
    report_json: Path
    report_markdown: Path
    paired_report_jsons: list[Path]
    observation_count: int
    objective_scale_ratio_median: float | None
    objective_scale_ratio_mean: float | None
    objective_scale_ratio_min: float | None
    objective_scale_ratio_max: float | None
    constraint_scale_ratio_median: float | None
    constraint_scale_ratio_mean: float | None
    recommended_sensitivity_multiplier_for_gradient_descent: float | None
    recommended_derivative_multiplier: float | None
    calibration_status: str
    gradient_descent_multiplier_votes: dict[str, int]
    observations: list[CalibrationObservation]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("output_dir", "report_json", "report_markdown"):
            data[key] = str(data[key])
        data["paired_report_jsons"] = [str(path) for path in self.paired_report_jsons]
        data["observations"] = [observation.to_dict() for observation in self.observations]
        data["schema_version"] = ADJOINT_DIRECTION_CHECK_SCHEMA_VERSION
        data["kind"] = "adjoint_calibration_summary"
        return data


def run_adjoint_direction_check(
    step_result_json: Path,
    *,
    output_dir: Path | None = None,
    sign_tolerance: float = 1.0e-9,
) -> AdjointDirectionCheckSummary:
    if sign_tolerance < 0.0:
        raise ValueError("sign_tolerance must be >= 0")
    step_result_json = step_result_json.resolve()
    step = json.loads(step_result_json.read_text(encoding="utf-8"))
    output_dir = output_dir or (step_result_json.parent / "adjoint_direction_check")
    output_dir.mkdir(parents=True, exist_ok=True)

    primal_cfd = _required_dict(step, "primal_cfd_summary")
    post_cfd = _required_dict(step, "post_update_primal_cfd_summary")
    density_step = _required_dict(step, "density_step")

    density_update_vti = _resolve_path(step_result_json.parent, str(density_step["density_update_vti"]))
    sensitivity_vti = _resolve_path(step_result_json.parent, str(step["sensitivity_vti"]))

    update_grid, update_arrays = read_density_update_vti(density_update_vti)
    sensitivity_grid, sensitivity_arrays = read_sensitivity_vti(sensitivity_vti)
    if update_grid.shape != sensitivity_grid.shape or not np.allclose(update_grid.origin, sensitivity_grid.origin) or abs(update_grid.spacing - sensitivity_grid.spacing) > 1.0e-12:
        raise ValueError("density_update_vti and sensitivity_vti grids do not match")

    active = update_arrays["active_mask"] > 0
    density_delta = update_arrays["density_delta"].astype(np.float64, copy=False)
    objective_gradient = update_arrays["objective_density_sensitivity"].astype(np.float64, copy=False)
    objective_contribution = np.where(active, objective_gradient * density_delta, 0.0)
    predicted_objective_delta = float(np.sum(objective_contribution[active]))

    initial_downforce = _required_float(primal_cfd, "downforce_coefficient")
    updated_downforce = _required_float(post_cfd, "downforce_coefficient")
    initial_objective = -initial_downforce
    updated_objective = -updated_downforce
    actual_objective_delta = float(updated_objective - initial_objective)
    objective_metric = _metric(
        name="raw_negative_downforce_objective",
        predicted_delta=predicted_objective_delta,
        actual_delta=actual_objective_delta,
        sign_tolerance=sign_tolerance,
    )

    constraint_metric = None
    initial_constraint = _optional_float(primal_cfd.get("efficiency_constraint"))
    updated_constraint = _optional_float(post_cfd.get("efficiency_constraint"))
    constraint_contribution = None
    if initial_constraint is not None and updated_constraint is not None:
        constraint_gradient = sensitivity_arrays["constraint_sensitivity"].astype(np.float64, copy=False)
        constraint_contribution = np.where(active, constraint_gradient * density_delta, 0.0)
        predicted_constraint_delta = float(np.sum(constraint_contribution[active]))
        actual_constraint_delta = float(updated_constraint - initial_constraint)
        constraint_metric = _metric(
            name="efficiency_constraint",
            predicted_delta=predicted_constraint_delta,
            actual_delta=actual_constraint_delta,
            sign_tolerance=sign_tolerance,
        )

    diagnostics_vti = output_dir / "adjoint_direction_check.vti"
    arrays: dict[str, np.ndarray] = {
        "active_mask": active.astype(np.uint8),
        "density_delta": density_delta.astype(np.float32),
        "objective_density_sensitivity": objective_gradient.astype(np.float32),
        "objective_direction_contribution": objective_contribution.astype(np.float32),
    }
    if constraint_contribution is not None:
        arrays["constraint_sensitivity"] = sensitivity_arrays["constraint_sensitivity"].astype(np.float32, copy=False)
        arrays["constraint_direction_contribution"] = constraint_contribution.astype(np.float32)
    write_vti_scalar_arrays(update_grid, arrays, diagnostics_vti)

    active_delta = density_delta[active]
    summary = AdjointDirectionCheckSummary(
        step_result_json=step_result_json,
        output_dir=output_dir,
        report_json=output_dir / "adjoint_direction_check.json",
        report_markdown=output_dir / "adjoint_direction_check.md",
        diagnostics_vti=diagnostics_vti,
        density_update_vti=density_update_vti,
        sensitivity_vti=sensitivity_vti,
        objective_metric=objective_metric,
        constraint_metric=constraint_metric,
        active_cell_count=int(active.sum()),
        density_delta_l2=float(np.linalg.norm(active_delta.ravel())) if active_delta.size else 0.0,
        density_delta_min=float(active_delta.min()) if active_delta.size else 0.0,
        density_delta_max=float(active_delta.max()) if active_delta.size else 0.0,
        initial_downforce_coefficient=initial_downforce,
        updated_downforce_coefficient=updated_downforce,
        initial_efficiency_constraint=initial_constraint,
        updated_efficiency_constraint=updated_constraint,
    )
    summary.report_json.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    summary.report_markdown.write_text(_summary_markdown(summary), encoding="utf-8")
    return summary


def run_paired_adjoint_direction_check(
    step_result_json: Path,
    *,
    output_dir: Path | None = None,
    execute_primal: bool = False,
    backend: str = "auto",
    timeout_seconds: int | None = None,
    reuse_existing_positive: bool = True,
    centered: bool = False,
    perturbation_scale: float = 1.0,
    sign_tolerance: float = 1.0e-9,
) -> PairedAdjointDirectionCheckSummary:
    if sign_tolerance < 0.0:
        raise ValueError("sign_tolerance must be >= 0")
    if perturbation_scale <= 0.0:
        raise ValueError("perturbation_scale must be > 0")
    step_result_json = step_result_json.resolve()
    step = json.loads(step_result_json.read_text(encoding="utf-8"))
    output_dir = output_dir or (step_result_json.parent / "paired_adjoint_direction_check")
    output_dir.mkdir(parents=True, exist_ok=True)

    primal_cfd = _required_dict(step, "primal_cfd_summary")
    density_step = _required_dict(step, "density_step")
    initial_downforce = _required_float(primal_cfd, "downforce_coefficient")
    initial_objective = -initial_downforce
    initial_constraint = _optional_float(primal_cfd.get("efficiency_constraint"))

    density_update_vti = _resolve_path(step_result_json.parent, str(density_step["density_update_vti"]))
    update_grid, update_arrays = read_density_update_vti(density_update_vti)
    old_density = update_arrays["density_old"].astype(np.float32, copy=False)
    base_delta = (update_arrays["density_delta"].astype(np.float32, copy=False) * float(perturbation_scale)).astype(np.float32)
    active = update_arrays["active_mask"] > 0
    objective_gradient = update_arrays["objective_density_sensitivity"].astype(np.float64, copy=False)

    sensitivity_vti = _resolve_path(step_result_json.parent, str(step["sensitivity_vti"]))
    _, sensitivity_arrays = read_sensitivity_vti(sensitivity_vti)
    constraint_gradient = sensitivity_arrays["constraint_sensitivity"].astype(np.float64, copy=False)

    source_project = _resolve_path(step_result_json.parent, str(density_step["project_yaml"]))
    perturbation_mode = "centered" if centered else "as_updated"
    if abs(float(perturbation_scale) - 1.0) > 1.0e-12:
        reuse_existing_positive = False
    baseline_design_state_json = None
    baseline_density_vti = None
    baseline_density_stl = None
    baseline_primal_case_dir = None
    baseline_primal_run = None
    baseline_primal_cfd_summary = None
    baseline_primal_error = None
    if centered:
        center_density = _center_density_for_symmetric_delta(old_density, base_delta, active)
        baseline = _write_density_design_variant(
            name="center",
            output_dir=output_dir,
            source_project=source_project,
            density=center_density,
            density_old=old_density,
            density_delta=center_density - old_density,
            active=active,
            objective_gradient=objective_gradient,
            constraint_gradient=constraint_gradient,
        )
        baseline_design_state_json = baseline["design_state_json"]
        baseline_density_vti = baseline["density_vti"]
        baseline_density_stl = baseline["density_stl"]
        old_density = center_density.astype(np.float32, copy=False)
        reuse_existing_positive = False
        if execute_primal:
            baseline_primal = run_primal_cfd_for_design_state(
                baseline_design_state_json,
                step_dir=Path(baseline["direction_dir"]) / "primal",
                backend=backend,
                timeout_seconds=timeout_seconds,
            )
            baseline_primal_case_dir = baseline_primal.case_dir
            baseline_primal_run = baseline_primal.run
            baseline_primal_cfd_summary = baseline_primal.cfd_summary
            baseline_primal_error = baseline_primal.error
            if baseline_primal.cfd_summary is not None:
                initial_downforce = _required_float(baseline_primal.cfd_summary, "downforce_coefficient")
                initial_objective = -initial_downforce
                initial_constraint = _optional_float(baseline_primal.cfd_summary.get("efficiency_constraint"))

    candidates: list[PairedDirectionCandidate] = []
    for name, multiplier in (("positive", 1.0), ("negative", -1.0)):
        candidate = _build_paired_candidate(
            name=name,
            multiplier=multiplier,
            output_dir=output_dir,
            source_project=source_project,
            old_density=old_density,
            base_delta=base_delta,
            active=active,
            objective_gradient=objective_gradient,
            constraint_gradient=constraint_gradient,
            initial_objective=initial_objective,
            initial_constraint=initial_constraint,
            step=step,
            execute_primal=execute_primal,
            backend=backend,
            timeout_seconds=timeout_seconds,
            reuse_existing_positive=reuse_existing_positive,
            sign_tolerance=sign_tolerance,
        )
        candidates.append(candidate)

    recommended = _select_recommended_candidate(candidates)
    recommended_multiplier = recommended.density_delta_multiplier if recommended is not None else None
    sensitivity_multiplier, sign_decision = _sensitivity_multiplier_decision(candidates, recommended)
    summary = PairedAdjointDirectionCheckSummary(
        step_result_json=step_result_json,
        output_dir=output_dir,
        report_json=output_dir / "paired_adjoint_direction_check.json",
        report_markdown=output_dir / "paired_adjoint_direction_check.md",
        perturbation_mode=perturbation_mode,
        perturbation_scale=float(perturbation_scale),
        baseline_design_state_json=baseline_design_state_json,
        baseline_density_vti=baseline_density_vti,
        baseline_density_stl=baseline_density_stl,
        baseline_primal_case_dir=baseline_primal_case_dir,
        baseline_primal_run=baseline_primal_run,
        baseline_primal_cfd_summary=baseline_primal_cfd_summary,
        baseline_primal_error=baseline_primal_error,
        initial_downforce_coefficient=initial_downforce,
        initial_efficiency_constraint=initial_constraint,
        active_cell_count=int(active.sum()),
        density_delta_l2=float(np.linalg.norm(base_delta[active].astype(np.float64).ravel())) if active.any() else 0.0,
        execute_primal=execute_primal,
        backend=backend,
        candidates=candidates,
        recommended_direction=recommended.name if recommended is not None else None,
        recommended_density_delta_multiplier=recommended_multiplier,
        suggested_sensitivity_multiplier_for_gradient_descent=sensitivity_multiplier,
        sensitivity_sign_decision=sign_decision,
    )
    summary.report_json.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    summary.report_markdown.write_text(_paired_summary_markdown(summary), encoding="utf-8")
    return summary


def run_adjoint_calibration_summary(
    paired_report_jsons: list[Path],
    *,
    output_dir: Path | None = None,
    min_density_delta_l2: float = 1.0e-12,
    min_abs_predicted_delta: float = 1.0e-12,
) -> AdjointCalibrationSummary:
    if not paired_report_jsons:
        raise ValueError("At least one paired_report_json is required")
    if min_density_delta_l2 < 0.0:
        raise ValueError("min_density_delta_l2 must be >= 0")
    if min_abs_predicted_delta < 0.0:
        raise ValueError("min_abs_predicted_delta must be >= 0")
    paired_report_jsons = [path.resolve() for path in paired_report_jsons]
    output_dir = output_dir or (paired_report_jsons[0].parent / "adjoint_calibration_summary")
    output_dir.mkdir(parents=True, exist_ok=True)

    observations: list[CalibrationObservation] = []
    votes: dict[str, int] = {}
    for report_path in paired_report_jsons:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        multiplier = _optional_float(report.get("suggested_sensitivity_multiplier_for_gradient_descent"))
        if report.get("sensitivity_sign_decision") == "paired_direction_selected" and multiplier is not None:
            vote_key = f"{multiplier:.12g}"
            votes[vote_key] = votes.get(vote_key, 0) + 1
        for candidate in report.get("candidates", []):
            observation = _observation_from_candidate(
                report_path=report_path,
                report=report,
                candidate=dict(candidate),
                min_density_delta_l2=min_density_delta_l2,
                min_abs_predicted_delta=min_abs_predicted_delta,
            )
            if observation is not None:
                observations.append(observation)

    objective_ratios = [observation.objective_scale_ratio for observation in observations]
    constraint_ratios = [
        observation.constraint_scale_ratio
        for observation in observations
        if observation.constraint_scale_ratio is not None
    ]
    recommended_gd = _recommended_vote(votes)
    objective_median = _stat_median(objective_ratios)
    status = _calibration_status(objective_median, recommended_gd, observations, paired_report_jsons)
    summary = AdjointCalibrationSummary(
        output_dir=output_dir,
        report_json=output_dir / "adjoint_calibration_summary.json",
        report_markdown=output_dir / "adjoint_calibration_summary.md",
        paired_report_jsons=paired_report_jsons,
        observation_count=len(observations),
        objective_scale_ratio_median=objective_median,
        objective_scale_ratio_mean=_stat_mean(objective_ratios),
        objective_scale_ratio_min=_stat_min(objective_ratios),
        objective_scale_ratio_max=_stat_max(objective_ratios),
        constraint_scale_ratio_median=_stat_median(constraint_ratios),
        constraint_scale_ratio_mean=_stat_mean(constraint_ratios),
        recommended_sensitivity_multiplier_for_gradient_descent=recommended_gd,
        recommended_derivative_multiplier=objective_median,
        calibration_status=status,
        gradient_descent_multiplier_votes=votes,
        observations=observations,
    )
    summary.report_json.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    summary.report_markdown.write_text(_calibration_summary_markdown(summary), encoding="utf-8")
    return summary


def _build_paired_candidate(
    *,
    name: str,
    multiplier: float,
    output_dir: Path,
    source_project: Path,
    old_density: np.ndarray,
    base_delta: np.ndarray,
    active: np.ndarray,
    objective_gradient: np.ndarray,
    constraint_gradient: np.ndarray,
    initial_objective: float,
    initial_constraint: float | None,
    step: dict[str, object],
    execute_primal: bool,
    backend: str,
    timeout_seconds: int | None,
    reuse_existing_positive: bool,
    sign_tolerance: float,
) -> PairedDirectionCandidate:
    density_delta = _bounded_delta(old_density, base_delta * float(multiplier), active)
    density_new = np.where(active, old_density + density_delta, old_density).astype(np.float32)
    variant = _write_density_design_variant(
        name=name,
        output_dir=output_dir,
        source_project=source_project,
        density=density_new,
        density_old=old_density,
        density_delta=density_delta,
        active=active,
        objective_gradient=objective_gradient,
        constraint_gradient=constraint_gradient,
    )
    direction_dir = Path(variant["direction_dir"])
    design_state_json = Path(variant["design_state_json"])
    density_update_vti = Path(variant["density_update_vti"])
    density_vti = Path(variant["density_vti"])
    density_stl = Path(variant["density_stl"])
    objective_contribution = np.asarray(variant["objective_contribution"], dtype=np.float64)
    constraint_contribution = np.asarray(variant["constraint_contribution"], dtype=np.float64)

    cfd_source = "not-run"
    primal_case_dir = None
    primal_run = None
    primal_cfd_summary = None
    primal_error = None
    if name == "positive" and reuse_existing_positive and step.get("post_update_primal_cfd_summary"):
        cfd_source = "step_post_update_primal"
        primal_case_raw = step.get("post_update_primal_case_dir")
        primal_case_dir = Path(str(primal_case_raw)) if primal_case_raw else None
        primal_run = dict(step["post_update_primal_run"]) if step.get("post_update_primal_run") else None
        primal_cfd_summary = dict(step["post_update_primal_cfd_summary"])
        primal_error = str(step["post_update_primal_error"]) if step.get("post_update_primal_error") else None
    elif execute_primal:
        cfd_source = "executed_primal"
        primal = run_primal_cfd_for_design_state(
            design_state_json,
            step_dir=direction_dir / "primal",
            backend=backend,
            timeout_seconds=timeout_seconds,
        )
        primal_case_dir = primal.case_dir
        primal_run = primal.run
        primal_cfd_summary = primal.cfd_summary
        primal_error = primal.error

    active_delta = density_delta[active]
    predicted_objective_delta = float(np.sum(objective_contribution[active]))
    predicted_constraint_delta = float(np.sum(constraint_contribution[active])) if initial_constraint is not None else None
    actual_objective_delta = None
    actual_constraint_delta = None
    objective_classification = "not_evaluated"
    constraint_classification = None
    if primal_cfd_summary is not None:
        actual_objective_delta = float(-_required_float(primal_cfd_summary, "downforce_coefficient") - initial_objective)
        objective_classification = _metric(
            name="raw_negative_downforce_objective",
            predicted_delta=predicted_objective_delta,
            actual_delta=actual_objective_delta,
            sign_tolerance=sign_tolerance,
        ).classification
        if initial_constraint is not None:
            updated_constraint = _optional_float(primal_cfd_summary.get("efficiency_constraint"))
            if updated_constraint is not None:
                actual_constraint_delta = float(updated_constraint - initial_constraint)
                constraint_classification = _metric(
                    name="efficiency_constraint",
                    predicted_delta=predicted_constraint_delta or 0.0,
                    actual_delta=actual_constraint_delta,
                    sign_tolerance=sign_tolerance,
                ).classification

    return PairedDirectionCandidate(
        name=name,
        density_delta_multiplier=float(multiplier),
        direction_dir=direction_dir,
        design_state_json=design_state_json,
        density_update_vti=density_update_vti,
        density_vti=density_vti,
        density_stl=density_stl,
        density_delta_l2=float(np.linalg.norm(active_delta.astype(np.float64).ravel())) if active_delta.size else 0.0,
        density_delta_min=float(active_delta.min()) if active_delta.size else 0.0,
        density_delta_max=float(active_delta.max()) if active_delta.size else 0.0,
        predicted_objective_delta=predicted_objective_delta,
        predicted_constraint_delta=predicted_constraint_delta,
        cfd_source=cfd_source,
        primal_case_dir=primal_case_dir,
        primal_run=primal_run,
        primal_cfd_summary=primal_cfd_summary,
        primal_error=primal_error,
        actual_objective_delta=actual_objective_delta,
        actual_constraint_delta=actual_constraint_delta,
        objective_classification=objective_classification,
        constraint_classification=constraint_classification,
    )


def _metric(
    *,
    name: str,
    predicted_delta: float,
    actual_delta: float,
    sign_tolerance: float,
) -> DirectionMetric:
    predicted_sign = _sign(predicted_delta, sign_tolerance)
    actual_sign = _sign(actual_delta, sign_tolerance)
    if predicted_sign == 0 or actual_sign == 0:
        sign_match = None
        classification = "indeterminate"
    else:
        sign_match = predicted_sign == actual_sign
        classification = "sign_match" if sign_match else "sign_mismatch"
    scale_ratio = None if abs(predicted_delta) <= sign_tolerance else float(actual_delta / predicted_delta)
    return DirectionMetric(
        name=name,
        predicted_delta=float(predicted_delta),
        actual_delta=float(actual_delta),
        sign_match=sign_match,
        scale_ratio=scale_ratio,
        classification=classification,
    )


def _summary_markdown(summary: AdjointDirectionCheckSummary) -> str:
    rows = [_metric_row(summary.objective_metric)]
    if summary.constraint_metric is not None:
        rows.append(_metric_row(summary.constraint_metric))
    metrics = "\n".join(rows)
    return f"""# Adjoint Direction Check

| Field | Value |
| --- | --- |
| Step result | `{summary.step_result_json}` |
| Active cells | {summary.active_cell_count} |
| Density delta L2 | {summary.density_delta_l2:.8g} |
| Density delta range | [{summary.density_delta_min:.8g}, {summary.density_delta_max:.8g}] |
| Initial downforce coefficient | {summary.initial_downforce_coefficient:.8g} |
| Updated downforce coefficient | {summary.updated_downforce_coefficient:.8g} |
| Initial efficiency constraint | {_format_optional(summary.initial_efficiency_constraint)} |
| Updated efficiency constraint | {_format_optional(summary.updated_efficiency_constraint)} |
| Diagnostics VTI | `{summary.diagnostics_vti}` |

## Direction Metrics

| Metric | Predicted delta | Actual delta | Sign match | Scale ratio | Classification |
| --- | ---: | ---: | --- | ---: | --- |
{metrics}
"""


def _metric_row(metric: DirectionMetric) -> str:
    sign_match = "indeterminate" if metric.sign_match is None else str(metric.sign_match).lower()
    scale_ratio = "" if metric.scale_ratio is None else f"{metric.scale_ratio:.8g}"
    return (
        f"| {metric.name} | {metric.predicted_delta:.8g} | {metric.actual_delta:.8g} | "
        f"{sign_match} | {scale_ratio} | {metric.classification} |"
    )


def _paired_summary_markdown(summary: PairedAdjointDirectionCheckSummary) -> str:
    rows = "\n".join(_paired_candidate_row(candidate) for candidate in summary.candidates)
    return f"""# Paired Adjoint Direction Check

| Field | Value |
| --- | --- |
| Step result | `{summary.step_result_json}` |
| Perturbation mode | {summary.perturbation_mode} |
| Perturbation scale | {summary.perturbation_scale:.8g} |
| Execute primal | {str(summary.execute_primal).lower()} |
| Backend | {summary.backend} |
| Baseline design state | `{summary.baseline_design_state_json or ''}` |
| Baseline primal CFD | {('ok' if summary.baseline_primal_cfd_summary else (summary.baseline_primal_error or 'not-run'))} |
| Active cells | {summary.active_cell_count} |
| Density delta L2 | {summary.density_delta_l2:.8g} |
| Initial downforce coefficient | {summary.initial_downforce_coefficient:.8g} |
| Initial efficiency constraint | {_format_optional(summary.initial_efficiency_constraint)} |
| Recommended direction | {summary.recommended_direction or ""} |
| Recommended density delta multiplier | {_format_optional(summary.recommended_density_delta_multiplier)} |
| Suggested sensitivity multiplier for gradient descent | {_format_optional(summary.suggested_sensitivity_multiplier_for_gradient_descent)} |
| Sensitivity sign decision | {summary.sensitivity_sign_decision} |

## Candidates

| Direction | Delta multiplier | Density delta L2 | Predicted objective delta | Actual objective delta | Objective classification | Predicted constraint delta | Actual constraint delta | Constraint classification | CFD source | Design state |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- | --- | --- |
{rows}
"""


def _paired_candidate_row(candidate: PairedDirectionCandidate) -> str:
    return (
        f"| {candidate.name} | {candidate.density_delta_multiplier:.8g} | "
        f"{candidate.density_delta_l2:.8g} | "
        f"{candidate.predicted_objective_delta:.8g} | {_format_optional(candidate.actual_objective_delta)} | "
        f"{candidate.objective_classification} | {_format_optional(candidate.predicted_constraint_delta)} | "
        f"{_format_optional(candidate.actual_constraint_delta)} | {candidate.constraint_classification or ''} | "
        f"{candidate.cfd_source} | `{candidate.design_state_json}` |"
    )


def _calibration_summary_markdown(summary: AdjointCalibrationSummary) -> str:
    rows = "\n".join(_calibration_observation_row(observation) for observation in summary.observations)
    return f"""# Adjoint Calibration Summary

| Field | Value |
| --- | --- |
| Paired reports | {len(summary.paired_report_jsons)} |
| Observations | {summary.observation_count} |
| Objective scale ratio median | {_format_optional(summary.objective_scale_ratio_median)} |
| Objective scale ratio mean | {_format_optional(summary.objective_scale_ratio_mean)} |
| Objective scale ratio range | [{_format_optional(summary.objective_scale_ratio_min)}, {_format_optional(summary.objective_scale_ratio_max)}] |
| Constraint scale ratio median | {_format_optional(summary.constraint_scale_ratio_median)} |
| Constraint scale ratio mean | {_format_optional(summary.constraint_scale_ratio_mean)} |
| Recommended sensitivity multiplier for gradient descent | {_format_optional(summary.recommended_sensitivity_multiplier_for_gradient_descent)} |
| Recommended derivative multiplier | {_format_optional(summary.recommended_derivative_multiplier)} |
| Calibration status | {summary.calibration_status} |

## Observations

| Report | Mode | Scale | Direction | Density delta L2 | Predicted objective delta | Actual objective delta | Objective scale ratio | Predicted constraint delta | Actual constraint delta | Constraint scale ratio |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{rows}
"""


def _calibration_observation_row(observation: CalibrationObservation) -> str:
    return (
        f"| `{observation.paired_report_json}` | {observation.perturbation_mode} | "
        f"{observation.perturbation_scale:.8g} | {observation.direction} | "
        f"{observation.density_delta_l2:.8g} | {observation.predicted_objective_delta:.8g} | "
        f"{observation.actual_objective_delta:.8g} | {observation.objective_scale_ratio:.8g} | "
        f"{_format_optional(observation.predicted_constraint_delta)} | "
        f"{_format_optional(observation.actual_constraint_delta)} | "
        f"{_format_optional(observation.constraint_scale_ratio)} |"
    )


def _observation_from_candidate(
    *,
    report_path: Path,
    report: dict[str, object],
    candidate: dict[str, object],
    min_density_delta_l2: float,
    min_abs_predicted_delta: float,
) -> CalibrationObservation | None:
    density_delta_l2 = float(candidate.get("density_delta_l2", 0.0))
    predicted = _optional_float(candidate.get("predicted_objective_delta"))
    actual = _optional_float(candidate.get("actual_objective_delta"))
    if density_delta_l2 <= min_density_delta_l2 or predicted is None or actual is None:
        return None
    if abs(predicted) <= min_abs_predicted_delta:
        return None
    predicted_constraint = _optional_float(candidate.get("predicted_constraint_delta"))
    actual_constraint = _optional_float(candidate.get("actual_constraint_delta"))
    constraint_ratio = None
    if predicted_constraint is not None and actual_constraint is not None and abs(predicted_constraint) > min_abs_predicted_delta:
        constraint_ratio = float(actual_constraint / predicted_constraint)
    return CalibrationObservation(
        paired_report_json=report_path,
        perturbation_mode=str(report.get("perturbation_mode", "")),
        perturbation_scale=float(report.get("perturbation_scale", 1.0)),
        direction=str(candidate.get("name", "")),
        density_delta_l2=density_delta_l2,
        predicted_objective_delta=float(predicted),
        actual_objective_delta=float(actual),
        objective_scale_ratio=float(actual / predicted),
        predicted_constraint_delta=predicted_constraint,
        actual_constraint_delta=actual_constraint,
        constraint_scale_ratio=constraint_ratio,
        objective_classification=str(candidate.get("objective_classification", "")),
        constraint_classification=str(candidate.get("constraint_classification")) if candidate.get("constraint_classification") is not None else None,
    )


def _recommended_vote(votes: dict[str, int]) -> float | None:
    if not votes:
        return None
    winner, count = max(votes.items(), key=lambda item: item[1])
    if list(votes.values()).count(count) > 1:
        return None
    return float(winner)


def _calibration_status(
    objective_median: float | None,
    recommended_gd: float | None,
    observations: list[CalibrationObservation],
    report_paths: list[Path],
) -> str:
    if len(report_paths) < 2:
        return "needs_multiple_reports"
    if not observations:
        return "no_valid_observations"
    if recommended_gd is None:
        return "no_consistent_search_direction"
    if objective_median is None:
        return "no_derivative_scale_estimate"
    if objective_median < 0.0:
        return "search_direction_consistent_derivative_opposite_sign"
    return "search_direction_consistent_derivative_same_sign"


def _stat_median(values: list[float]) -> float | None:
    return float(np.median(np.array(values, dtype=float))) if values else None


def _stat_mean(values: list[float]) -> float | None:
    return float(np.mean(np.array(values, dtype=float))) if values else None


def _stat_min(values: list[float]) -> float | None:
    return float(np.min(np.array(values, dtype=float))) if values else None


def _stat_max(values: list[float]) -> float | None:
    return float(np.max(np.array(values, dtype=float))) if values else None


def _write_density_design_variant(
    *,
    name: str,
    output_dir: Path,
    source_project: Path,
    density: np.ndarray,
    density_old: np.ndarray,
    density_delta: np.ndarray,
    active: np.ndarray,
    objective_gradient: np.ndarray,
    constraint_gradient: np.ndarray,
) -> dict[str, object]:
    direction_dir = output_dir / name
    if direction_dir.exists():
        shutil.rmtree(direction_dir)
    direction_dir.mkdir(parents=True, exist_ok=True)
    project_yaml = _copy_project_for_direction(source_project, direction_dir)
    config = load_project(project_yaml)
    bundle = build_fields(config)

    objective_contribution = np.where(active, objective_gradient * density_delta.astype(np.float64), 0.0)
    constraint_contribution = np.where(active, constraint_gradient * density_delta.astype(np.float64), 0.0)
    density_update_vti = direction_dir / "density_update.vti"
    write_vti_scalar_arrays(
        bundle.grid,
        {
            "density_old": density_old.astype(np.float32, copy=False),
            "density_new": density.astype(np.float32, copy=False),
            "density_delta": density_delta.astype(np.float32, copy=False),
            "objective_density_sensitivity": objective_gradient.astype(np.float32),
            "objective_direction_contribution": objective_contribution.astype(np.float32),
            "constraint_sensitivity": constraint_gradient.astype(np.float32),
            "constraint_direction_contribution": constraint_contribution.astype(np.float32),
            "active_mask": active.astype(np.uint8),
        },
        density_update_vti,
    )

    density_vti = direction_dir / "density.vti"
    density_stl = direction_dir / "geometry" / "front_wing_initial.stl"
    export_density_vti(bundle, density, density_vti)
    export_density_stl(bundle, density, density_stl)
    design_state_json = direction_dir / "design_state.json"
    design_state = create_density_design_state(
        bundle=bundle,
        density=density,
        density_vti=density_vti,
        derived_geometry=density_stl,
        source_project=project_yaml,
        created_by="cfd_sdf.adjoint_calibration",
    )
    write_density_design_state(design_state, design_state_json)
    return {
        "direction_dir": direction_dir,
        "design_state_json": design_state_json,
        "density_update_vti": density_update_vti,
        "density_vti": density_vti,
        "density_stl": density_stl,
        "objective_contribution": objective_contribution,
        "constraint_contribution": constraint_contribution,
    }


def _center_density_for_symmetric_delta(old_density: np.ndarray, base_delta: np.ndarray, active: np.ndarray) -> np.ndarray:
    radius = np.abs(base_delta.astype(np.float32, copy=False))
    lower = radius
    upper = 1.0 - radius
    centered = np.clip(old_density.astype(np.float32, copy=False), lower, upper)
    return np.where(active, centered, old_density).astype(np.float32)


def _bounded_delta(old_density: np.ndarray, requested_delta: np.ndarray, active: np.ndarray) -> np.ndarray:
    target = np.clip(old_density.astype(np.float32, copy=False) + requested_delta.astype(np.float32, copy=False), 0.0, 1.0)
    return np.where(active, target - old_density, 0.0).astype(np.float32)


def _copy_project_for_direction(source_project: Path, direction_dir: Path) -> Path:
    source_project = source_project.resolve()
    target_project = direction_dir / "project.yaml"
    shutil.copy2(source_project, target_project)
    source_geometry = source_project.parent / "geometry"
    target_geometry = direction_dir / "geometry"
    if target_geometry.exists():
        shutil.rmtree(target_geometry)
    if source_geometry.exists():
        shutil.copytree(source_geometry, target_geometry)
    else:
        target_geometry.mkdir(parents=True, exist_ok=True)
    return target_project


def _select_recommended_candidate(candidates: list[PairedDirectionCandidate]) -> PairedDirectionCandidate | None:
    evaluated = [
        candidate
        for candidate in candidates
        if candidate.actual_objective_delta is not None and candidate.primal_error is None
    ]
    if len(evaluated) < 2:
        return None
    return min(evaluated, key=lambda candidate: float(candidate.actual_objective_delta))


def _sensitivity_multiplier_decision(
    candidates: list[PairedDirectionCandidate],
    recommended: PairedDirectionCandidate | None,
) -> tuple[float | None, str]:
    if recommended is None:
        return None, "insufficient_primal_evaluations"
    evaluated = [
        candidate
        for candidate in candidates
        if candidate.actual_objective_delta is not None and candidate.primal_error is None
    ]
    if any(candidate.density_delta_l2 <= 1.0e-12 for candidate in evaluated):
        return None, "insufficient_symmetric_density_motion"
    return recommended.density_delta_multiplier, "paired_direction_selected"


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return (base_dir / path).resolve()


def _required_dict(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Step result is missing required object: {key}")
    return value


def _required_float(data: dict[str, object], key: str) -> float:
    value = _optional_float(data.get(key))
    if value is None:
        raise ValueError(f"CFD summary is missing required numeric value: {key}")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _sign(value: float, tolerance: float) -> int:
    if abs(value) <= tolerance:
        return 0
    return 1 if value > 0.0 else -1


def _format_optional(value: float | None) -> str:
    return "" if value is None else f"{value:.8g}"
