from __future__ import annotations

import json
import shutil
from csv import DictWriter
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import yaml
from scipy.ndimage import gaussian_filter, uniform_filter

from .candidate_constraints import ConstraintRecord, build_constraint_records, constraint_penalty
from .config import load_project
from .constraints import check_constraints
from .design_state import create_density_design_state, resolve_design_state_path, write_density_design_state
from .export_vtk import export_vti, export_zero_surface
from .sensitivity import (
    DensityStateData,
    load_density_state,
    read_sensitivity_vti,
    write_mock_sensitivity_artifacts,
    write_vti_scalar_arrays,
)
from .sdf import FieldBundle, build_fields
from .topology import TopologyControls, export_density_stl, export_density_vti, low_fidelity_topology_aero


@dataclass(frozen=True)
class DensityOptimizerControls:
    move_limit: float = 0.05
    step_size: float = 1.0
    density_lower: float = 0.0
    density_upper: float = 1.0
    volume_fraction_min: float = 0.05
    volume_fraction_max: float = 0.55
    smoothing_radius_cells: float = 1.0
    minimum_thickness_radius_cells: int = 1
    minimum_thickness_neighbor_fraction: float = 0.25
    root_preserve_distance_m: float = 0.12
    heavi_beta: float = 0.0
    heavi_eta: float = 0.5
    sensitivity_update_multiplier: float = 1.0
    sensitivity_derivative_multiplier: float | None = None
    constraint_sensitivity_weight: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DensityStepResult:
    index: int
    step_dir: Path
    input_design_state_json: Path
    output_design_state_json: Path
    project_yaml: Path
    sensitivity_vti: Path
    sensitivity_summary_json: Path
    density_update_vti: Path
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
    volume_fraction: float
    active_cell_count: int
    density_delta_min: float
    density_delta_max: float
    density_delta_l2: float
    root_anchor_cell_count: int
    thin_cell_penalty_count: int

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "step_dir",
            "input_design_state_json",
            "output_design_state_json",
            "project_yaml",
            "sensitivity_vti",
            "sensitivity_summary_json",
            "density_update_vti",
            "density_vti",
            "density_stl",
        ):
            data[key] = str(data[key])
        data["constraint_records"] = [record.to_dict() for record in self.constraint_records]
        return data


@dataclass(frozen=True)
class DensityOptimizationSummary:
    run_dir: Path
    iterations: int
    accepted_count: int
    best_step: DensityStepResult
    steps: list[DensityStepResult]
    history_csv: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "run_dir": str(self.run_dir),
            "iterations": self.iterations,
            "accepted_count": self.accepted_count,
            "best_step": self.best_step.to_dict(),
            "history_csv": str(self.history_csv),
            "steps": [step.to_dict() for step in self.steps],
        }


def run_density_optimization(
    initial_design_state_json: Path,
    *,
    run_dir: Path,
    iterations: int,
    controls: DensityOptimizerControls | None = None,
    resume: bool = False,
) -> DensityOptimizationSummary:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    controls = controls or DensityOptimizerControls()
    _validate_controls(controls)

    run_dir.mkdir(parents=True, exist_ok=True)
    current_design_state = initial_design_state_json
    steps: list[DensityStepResult] = []
    for index in range(iterations):
        step_dir = run_dir / f"density_step_{index:04d}"
        result_path = step_dir / "density_step_result.json"
        if resume and result_path.exists():
            result = _step_result_from_dict(json.loads(result_path.read_text(encoding="utf-8")))
            steps.append(result)
            current_design_state = result.output_design_state_json
            continue
        result = run_density_update_step(
            current_design_state,
            step_dir=step_dir,
            index=index,
            controls=controls,
        )
        steps.append(result)
        result_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        current_design_state = result.output_design_state_json

    history_csv = run_dir / "density_optimization_history.csv"
    _write_history(history_csv, steps)
    best = _select_best(steps)
    summary = DensityOptimizationSummary(
        run_dir=run_dir,
        iterations=iterations,
        accepted_count=sum(1 for step in steps if step.status == "accepted"),
        best_step=best,
        steps=steps,
        history_csv=history_csv,
    )
    (run_dir / "density_optimization_summary.json").write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    _promote_best(run_dir, best)
    return summary


def run_density_update_step(
    input_design_state_json: Path,
    *,
    step_dir: Path,
    index: int,
    controls: DensityOptimizerControls,
) -> DensityStepResult:
    _validate_controls(controls)
    step_dir.mkdir(parents=True, exist_ok=True)
    density_state = load_density_state(input_design_state_json)
    project_yaml = _copy_source_project(density_state, step_dir)
    source_config = load_project(project_yaml)
    source_bundle = build_fields(source_config)
    _assert_compatible_grid(density_state, source_bundle)

    sensitivity = write_mock_sensitivity_artifacts(density_state.design_state_json, output_dir=step_dir)
    _, sensitivity_arrays = read_sensitivity_vti(sensitivity.sensitivity_vti)
    raw_objective_sensitivity = sensitivity_arrays["objective_density_sensitivity"].astype(np.float32, copy=False)
    active_mask = sensitivity_arrays["active_mask"] > 0
    effective_controls, constraint_blend_policy = _constraint_blend_controls(
        controls,
        sensitivity.sensitivity_summary_json,
    )
    effective_objective_sensitivity = _effective_update_sensitivity(raw_objective_sensitivity, effective_controls)
    update_sensitivity, constraint_sensitivity, effective_constraint_sensitivity = _combine_update_sensitivity(
        raw_objective_sensitivity=raw_objective_sensitivity,
        effective_objective_sensitivity=effective_objective_sensitivity,
        constraint_sensitivity=sensitivity_arrays.get("constraint_sensitivity"),
        active_mask=active_mask & density_state.allowed_mask,
        controls=effective_controls,
    )
    density_new, density_delta, update_metrics = compute_density_update(
        density_state,
        source_bundle,
        update_sensitivity,
        active_mask,
        controls,
    )

    density_update_vti = step_dir / "density_update.vti"
    write_vti_scalar_arrays(
        density_state.grid,
        {
            "density_old": density_state.density.astype(np.float32, copy=False),
            "density_new": density_new,
            "density_delta": density_delta,
            **_density_update_sensitivity_arrays(
                raw_objective_sensitivity,
                effective_objective_sensitivity,
                update_sensitivity,
                constraint_sensitivity,
                effective_constraint_sensitivity,
                effective_controls,
            ),
            "active_mask": active_mask.astype(np.uint8),
            "thickness_proxy": update_metrics["thickness_proxy"].astype(np.float32, copy=False),
            "root_anchor_mask": update_metrics["root_anchor_mask"].astype(np.uint8),
        },
        density_update_vti,
    )

    density_vti = step_dir / "density.vti"
    legacy_density_vti = step_dir / "density_field.vti"
    density_stl = step_dir / "geometry" / "front_wing_initial.stl"
    export_density_vti(source_bundle, density_new, density_vti)
    export_density_vti(source_bundle, density_new, legacy_density_vti)
    export_density_stl(source_bundle, density_new, density_stl)
    output_design_state_json = step_dir / "design_state.json"
    design_state = create_density_design_state(
        bundle=source_bundle,
        density=density_new,
        density_vti=density_vti,
        derived_geometry=density_stl,
        source_project=project_yaml,
        created_by="cfd_sdf.density_optimizer",
    )
    write_density_design_state(design_state, output_design_state_json)

    updated_config = load_project(project_yaml)
    updated_bundle = build_fields(updated_config)
    report, derived = check_constraints(updated_config, updated_bundle)
    updated_config.resolved_output_dir.mkdir(parents=True, exist_ok=True)
    (updated_config.resolved_output_dir / "report.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    export_vti(updated_bundle, updated_config.resolved_output_dir, derived)
    export_zero_surface(updated_bundle, updated_config.resolved_output_dir)

    aero = low_fidelity_topology_aero(density_new, source_bundle, updated_config, TopologyControls())
    records = build_constraint_records(report.to_dict(), aero, updated_config)
    enforced_failures = [record for record in records if record.enforced and not record.satisfied]
    rejection_reasons = [record.name for record in enforced_failures]
    status = "rejected" if rejection_reasons else "accepted"
    penalty = constraint_penalty(records)
    objective = -aero["downforce_coefficient"] + penalty
    active_count = int(density_state.allowed_mask.sum())
    solid_count = int((density_new >= 0.5).sum())
    active_delta = density_delta[density_state.allowed_mask]

    return DensityStepResult(
        index=index,
        step_dir=step_dir,
        input_design_state_json=density_state.design_state_json,
        output_design_state_json=output_design_state_json,
        project_yaml=project_yaml,
        sensitivity_vti=sensitivity.sensitivity_vti,
        sensitivity_summary_json=sensitivity.sensitivity_summary_json,
        density_update_vti=density_update_vti,
        density_vti=density_vti,
        density_stl=density_stl,
        controls=_controls_with_constraint_blend_policy(controls, effective_controls, constraint_blend_policy),
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
        solid_fraction=float(solid_count / active_count) if active_count else 0.0,
        volume_fraction=float(np.mean(density_new[density_state.allowed_mask])) if active_count else 0.0,
        active_cell_count=active_count,
        density_delta_min=float(active_delta.min()) if active_delta.size else 0.0,
        density_delta_max=float(active_delta.max()) if active_delta.size else 0.0,
        density_delta_l2=float(np.linalg.norm(active_delta.ravel())) if active_delta.size else 0.0,
        root_anchor_cell_count=int(update_metrics["root_anchor_mask"].sum()),
        thin_cell_penalty_count=int(update_metrics["thin_cell_penalty_count"]),
    )


def run_density_update_step_from_sensitivity(
    input_design_state_json: Path,
    *,
    step_dir: Path,
    index: int,
    controls: DensityOptimizerControls,
    sensitivity_vti: Path,
    sensitivity_summary_json: Path,
) -> DensityStepResult:
    _validate_controls(controls)
    step_dir.mkdir(parents=True, exist_ok=True)
    density_state = load_density_state(input_design_state_json)
    project_yaml = _copy_source_project(density_state, step_dir)
    source_config = load_project(project_yaml)
    source_bundle = build_fields(source_config)
    _assert_compatible_grid(density_state, source_bundle)

    _, sensitivity_arrays = read_sensitivity_vti(sensitivity_vti)
    raw_objective_sensitivity = sensitivity_arrays["objective_density_sensitivity"].astype(np.float32, copy=False)
    active_mask = sensitivity_arrays["active_mask"] > 0
    effective_controls, constraint_blend_policy = _constraint_blend_controls(
        controls,
        sensitivity_summary_json,
    )
    effective_objective_sensitivity = _effective_update_sensitivity(raw_objective_sensitivity, effective_controls)
    update_sensitivity, constraint_sensitivity, effective_constraint_sensitivity = _combine_update_sensitivity(
        raw_objective_sensitivity=raw_objective_sensitivity,
        effective_objective_sensitivity=effective_objective_sensitivity,
        constraint_sensitivity=sensitivity_arrays.get("constraint_sensitivity"),
        active_mask=active_mask & density_state.allowed_mask,
        controls=effective_controls,
    )
    density_new, density_delta, update_metrics = compute_density_update(
        density_state,
        source_bundle,
        update_sensitivity,
        active_mask,
        controls,
    )

    density_update_vti = step_dir / "density_update.vti"
    write_vti_scalar_arrays(
        density_state.grid,
        {
            "density_old": density_state.density.astype(np.float32, copy=False),
            "density_new": density_new,
            "density_delta": density_delta,
            **_density_update_sensitivity_arrays(
                raw_objective_sensitivity,
                effective_objective_sensitivity,
                update_sensitivity,
                constraint_sensitivity,
                effective_constraint_sensitivity,
                effective_controls,
            ),
            "active_mask": active_mask.astype(np.uint8),
            "thickness_proxy": update_metrics["thickness_proxy"].astype(np.float32, copy=False),
            "root_anchor_mask": update_metrics["root_anchor_mask"].astype(np.uint8),
        },
        density_update_vti,
    )

    density_vti = step_dir / "density.vti"
    legacy_density_vti = step_dir / "density_field.vti"
    density_stl = step_dir / "geometry" / "front_wing_initial.stl"
    export_density_vti(source_bundle, density_new, density_vti)
    export_density_vti(source_bundle, density_new, legacy_density_vti)
    export_density_stl(source_bundle, density_new, density_stl)
    output_design_state_json = step_dir / "design_state.json"
    design_state = create_density_design_state(
        bundle=source_bundle,
        density=density_new,
        density_vti=density_vti,
        derived_geometry=density_stl,
        source_project=project_yaml,
        created_by="cfd_sdf.density_optimizer",
    )
    write_density_design_state(design_state, output_design_state_json)

    updated_config = load_project(project_yaml)
    updated_bundle = build_fields(updated_config)
    report, derived = check_constraints(updated_config, updated_bundle)
    updated_config.resolved_output_dir.mkdir(parents=True, exist_ok=True)
    (updated_config.resolved_output_dir / "report.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    export_vti(updated_bundle, updated_config.resolved_output_dir, derived)
    export_zero_surface(updated_bundle, updated_config.resolved_output_dir)

    aero = low_fidelity_topology_aero(density_new, source_bundle, updated_config, TopologyControls())
    records = build_constraint_records(report.to_dict(), aero, updated_config)
    enforced_failures = [record for record in records if record.enforced and not record.satisfied]
    rejection_reasons = [record.name for record in enforced_failures]
    status = "rejected" if rejection_reasons else "accepted"
    penalty = constraint_penalty(records)
    objective = -aero["downforce_coefficient"] + penalty
    active_count = int(density_state.allowed_mask.sum())
    solid_count = int((density_new >= 0.5).sum())
    active_delta = density_delta[density_state.allowed_mask]

    return DensityStepResult(
        index=index,
        step_dir=step_dir,
        input_design_state_json=density_state.design_state_json,
        output_design_state_json=output_design_state_json,
        project_yaml=project_yaml,
        sensitivity_vti=sensitivity_vti,
        sensitivity_summary_json=sensitivity_summary_json,
        density_update_vti=density_update_vti,
        density_vti=density_vti,
        density_stl=density_stl,
        controls=_controls_with_constraint_blend_policy(controls, effective_controls, constraint_blend_policy),
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
        solid_fraction=float(solid_count / active_count) if active_count else 0.0,
        volume_fraction=float(np.mean(density_new[density_state.allowed_mask])) if active_count else 0.0,
        active_cell_count=active_count,
        density_delta_min=float(active_delta.min()) if active_delta.size else 0.0,
        density_delta_max=float(active_delta.max()) if active_delta.size else 0.0,
        density_delta_l2=float(np.linalg.norm(active_delta.ravel())) if active_delta.size else 0.0,
        root_anchor_cell_count=int(update_metrics["root_anchor_mask"].sum()),
        thin_cell_penalty_count=int(update_metrics["thin_cell_penalty_count"]),
    )


def compute_density_update(
    density_state: DensityStateData,
    source_bundle: FieldBundle,
    objective_sensitivity: np.ndarray,
    sensitivity_active_mask: np.ndarray,
    controls: DensityOptimizerControls,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray | int]]:
    old_density = density_state.density.astype(np.float32, copy=False)
    active = density_state.allowed_mask & sensitivity_active_mask
    gradient = objective_sensitivity.astype(np.float32, copy=False)
    active_gradient = np.abs(gradient[active])
    scale = float(active_gradient.max()) if active_gradient.size else 0.0
    scale = scale if scale > 1.0e-12 else 1.0

    density = old_density.copy()
    density[active] += -controls.step_size * controls.move_limit * gradient[active] / scale
    density = np.clip(density, controls.density_lower, controls.density_upper)
    density = np.where(density_state.allowed_mask, density, 0.0).astype(np.float32)

    density = _apply_smoothing(density, density_state.allowed_mask, controls.smoothing_radius_cells)
    thickness_proxy = _thickness_proxy(density, controls.minimum_thickness_radius_cells)
    density, thin_count = _apply_minimum_thickness_proxy(
        density,
        density_state.allowed_mask,
        thickness_proxy,
        controls.minimum_thickness_neighbor_fraction,
    )
    root_anchor = _root_anchor_mask(source_bundle, density_state.allowed_mask, controls.root_preserve_distance_m)
    density[root_anchor] = np.maximum(density[root_anchor], old_density[root_anchor])
    density = _apply_volume_fraction_bounds(density, density_state.allowed_mask, controls)
    density = _apply_heaviside_projection(density, density_state.allowed_mask, controls.heavi_beta, controls.heavi_eta)

    raw_delta = density - old_density
    limited_delta = np.clip(raw_delta, -controls.move_limit, controls.move_limit)
    density_new = np.clip(old_density + limited_delta, controls.density_lower, controls.density_upper)
    density_new = np.where(density_state.allowed_mask, density_new, 0.0).astype(np.float32)
    density_delta = (density_new - old_density).astype(np.float32)
    return density_new, density_delta, {
        "thickness_proxy": thickness_proxy.astype(np.float32),
        "root_anchor_mask": root_anchor.astype(np.uint8),
        "thin_cell_penalty_count": int(thin_count),
    }


def _effective_update_sensitivity(
    raw_objective_sensitivity: np.ndarray,
    controls: DensityOptimizerControls,
) -> np.ndarray:
    return (
        raw_objective_sensitivity.astype(np.float32, copy=False)
        * np.float32(controls.sensitivity_update_multiplier)
    ).astype(np.float32)


def _combine_update_sensitivity(
    *,
    raw_objective_sensitivity: np.ndarray,
    effective_objective_sensitivity: np.ndarray,
    constraint_sensitivity: np.ndarray | None,
    active_mask: np.ndarray,
    controls: DensityOptimizerControls,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    if controls.constraint_sensitivity_weight <= 0.0 or constraint_sensitivity is None:
        return effective_objective_sensitivity.astype(np.float32, copy=False), None, None

    raw_constraint = constraint_sensitivity.astype(np.float32, copy=False)
    effective_constraint = _normalize_like(
        raw_constraint,
        effective_objective_sensitivity,
        active_mask,
    )
    combined = (
        effective_objective_sensitivity.astype(np.float32, copy=False)
        + np.float32(controls.constraint_sensitivity_weight) * effective_constraint
    ).astype(np.float32)
    return combined, raw_constraint, effective_constraint


def _constraint_blend_controls(
    controls: DensityOptimizerControls,
    sensitivity_summary_json: Path,
) -> tuple[DensityOptimizerControls, dict[str, object]]:
    policy = _constraint_blend_policy(sensitivity_summary_json, controls.constraint_sensitivity_weight)
    effective_weight = float(policy["effective_constraint_sensitivity_weight"])
    if effective_weight == float(controls.constraint_sensitivity_weight):
        return controls, policy
    return replace(controls, constraint_sensitivity_weight=effective_weight), policy


def _constraint_blend_policy(
    sensitivity_summary_json: Path,
    requested_weight: float,
) -> dict[str, object]:
    requested = float(requested_weight)
    base: dict[str, object] = {
        "summary_path": str(sensitivity_summary_json),
        "requested_constraint_sensitivity_weight": requested,
        "effective_constraint_sensitivity_weight": requested,
    }
    if requested <= 0.0:
        return {
            **base,
            "mode": "disabled_by_user",
            "note": "Constraint sensitivity blending was not requested.",
        }

    try:
        summary = json.loads(sensitivity_summary_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            **base,
            "effective_constraint_sensitivity_weight": 0.0,
            "mode": "disabled_summary_unavailable",
            "note": f"Constraint blend disabled because sensitivity summary could not be read: {exc}",
        }

    status = summary.get("constraint_sensitivity_status")
    diagnostics = summary.get("constraint_sensitivity_diagnostics")
    usable = diagnostics.get("usable_for_efficiency_constraint_update") if isinstance(diagnostics, dict) else None
    base.update(
        {
            "constraint_sensitivity_status": status,
            "usable_for_efficiency_constraint_update": usable,
        }
    )
    if status is None and usable is None:
        return {
            **base,
            "mode": "active_legacy_summary_without_diagnostics",
            "note": "Constraint blend allowed for a legacy sensitivity summary without diagnostics.",
        }
    if usable is False or status != "available":
        return {
            **base,
            "effective_constraint_sensitivity_weight": 0.0,
            "mode": "disabled_unusable_constraint_sensitivity",
            "note": (
                "Constraint blend disabled because the sensitivity summary "
                f"reported status={status!r}."
            ),
        }
    return {
        **base,
        "mode": "active",
        "note": "Constraint blend enabled by sensitivity summary diagnostics.",
    }


def _controls_with_constraint_blend_policy(
    requested_controls: DensityOptimizerControls,
    effective_controls: DensityOptimizerControls,
    policy: dict[str, object],
) -> dict[str, object]:
    controls = requested_controls.to_dict()
    controls["effective_constraint_sensitivity_weight"] = effective_controls.constraint_sensitivity_weight
    controls["constraint_sensitivity_blend_policy"] = policy
    return controls


def _normalize_like(source: np.ndarray, reference: np.ndarray, active_mask: np.ndarray) -> np.ndarray:
    active = active_mask.astype(bool, copy=False)
    source_active = np.abs(source[active])
    reference_active = np.abs(reference[active])
    source_scale = float(source_active.max()) if source_active.size else 0.0
    reference_scale = float(reference_active.max()) if reference_active.size else 0.0
    if source_scale <= 1.0e-12:
        return np.zeros_like(source, dtype=np.float32)
    if reference_scale <= 1.0e-12:
        reference_scale = 1.0
    return (source.astype(np.float32, copy=False) * np.float32(reference_scale / source_scale)).astype(np.float32)


def _density_update_sensitivity_arrays(
    raw_objective_sensitivity: np.ndarray,
    effective_objective_sensitivity: np.ndarray,
    update_sensitivity: np.ndarray,
    constraint_sensitivity: np.ndarray | None,
    effective_constraint_sensitivity: np.ndarray | None,
    controls: DensityOptimizerControls,
) -> dict[str, np.ndarray]:
    arrays = {
        "objective_density_sensitivity": update_sensitivity.astype(np.float32, copy=False),
        "base_objective_density_sensitivity": effective_objective_sensitivity.astype(np.float32, copy=False),
        "raw_objective_density_sensitivity": raw_objective_sensitivity.astype(np.float32, copy=False),
    }
    if constraint_sensitivity is not None and effective_constraint_sensitivity is not None:
        arrays["raw_constraint_sensitivity"] = constraint_sensitivity.astype(np.float32, copy=False)
        arrays["effective_constraint_sensitivity"] = effective_constraint_sensitivity.astype(np.float32, copy=False)
        arrays["combined_update_sensitivity"] = update_sensitivity.astype(np.float32, copy=False)
    if controls.sensitivity_derivative_multiplier is not None:
        arrays["objective_derivative_sensitivity"] = (
            raw_objective_sensitivity.astype(np.float32, copy=False)
            * np.float32(controls.sensitivity_derivative_multiplier)
        ).astype(np.float32)
    return arrays


def _copy_source_project(density_state: DensityStateData, step_dir: Path) -> Path:
    source_project = resolve_design_state_path(
        density_state.design_state_json,
        density_state.state.source_project,
        local_fallback=Path("project.yaml"),
    )
    source_dir = source_project.parent
    geometry_source = source_dir / "geometry"
    geometry_target = step_dir / "geometry"
    if geometry_target.exists():
        shutil.rmtree(geometry_target)
    shutil.copytree(geometry_source, geometry_target)

    project_data = yaml.safe_load(source_project.read_text(encoding="utf-8")) or {}
    project_data["output_dir"] = "runs/front_wing_demo"
    project_yaml = step_dir / "project.yaml"
    project_yaml.write_text(yaml.safe_dump(project_data, sort_keys=False), encoding="utf-8")
    return project_yaml


def _apply_smoothing(density: np.ndarray, active: np.ndarray, radius_cells: float) -> np.ndarray:
    if radius_cells <= 0.0:
        return density
    smoothed = gaussian_filter(density, sigma=float(radius_cells), mode="nearest")
    normalizer = gaussian_filter(active.astype(np.float32), sigma=float(radius_cells), mode="nearest")
    normalizer = np.where(normalizer > 1.0e-6, normalizer, 1.0)
    result = smoothed / normalizer
    return np.where(active, result, 0.0).astype(np.float32)


def _thickness_proxy(density: np.ndarray, radius_cells: int) -> np.ndarray:
    if radius_cells <= 0:
        return density.astype(np.float32, copy=False)
    size = 2 * int(radius_cells) + 1
    return uniform_filter(density.astype(np.float32), size=size, mode="nearest").astype(np.float32)


def _apply_minimum_thickness_proxy(
    density: np.ndarray,
    active: np.ndarray,
    thickness_proxy: np.ndarray,
    neighbor_fraction: float,
) -> tuple[np.ndarray, int]:
    if neighbor_fraction <= 0.0:
        return density, 0
    sparse = active & (density > 0.05) & (thickness_proxy < neighbor_fraction)
    result = density.copy()
    result[sparse] *= np.clip(thickness_proxy[sparse] / neighbor_fraction, 0.0, 1.0)
    return result.astype(np.float32), int(sparse.sum())


def _root_anchor_mask(bundle: FieldBundle, active: np.ndarray, distance_m: float) -> np.ndarray:
    root_phi = bundle.arrays.get("root_phi")
    if root_phi is None or root_phi.shape != active.shape or distance_m < 0.0:
        return np.zeros(active.shape, dtype=bool)
    return active & (root_phi <= distance_m)


def _apply_volume_fraction_bounds(
    density: np.ndarray,
    active: np.ndarray,
    controls: DensityOptimizerControls,
) -> np.ndarray:
    active_values = density[active]
    if not active_values.size:
        return density
    mean_value = float(active_values.mean())
    target = mean_value
    if mean_value > controls.volume_fraction_max:
        target = controls.volume_fraction_max
    elif mean_value < controls.volume_fraction_min:
        target = controls.volume_fraction_min
    if np.isclose(target, mean_value):
        return density
    scale = target / max(mean_value, 1.0e-12)
    result = density.copy()
    result[active] = np.clip(result[active] * scale, controls.density_lower, controls.density_upper)
    return result.astype(np.float32)


def _apply_heaviside_projection(density: np.ndarray, active: np.ndarray, beta: float, eta: float) -> np.ndarray:
    if beta <= 0.0:
        return density
    numerator = np.tanh(beta * eta) + np.tanh(beta * (density - eta))
    denominator = np.tanh(beta * eta) + np.tanh(beta * (1.0 - eta))
    projected = numerator / max(float(denominator), 1.0e-12)
    return np.where(active, np.clip(projected, 0.0, 1.0), 0.0).astype(np.float32)


def _validate_controls(controls: DensityOptimizerControls) -> None:
    if controls.move_limit < 0.0:
        raise ValueError("move_limit must be >= 0")
    if controls.density_lower > controls.density_upper:
        raise ValueError("density_lower must be <= density_upper")
    if not 0.0 <= controls.volume_fraction_min <= controls.volume_fraction_max <= 1.0:
        raise ValueError("volume fraction bounds must satisfy 0 <= min <= max <= 1")
    if controls.minimum_thickness_neighbor_fraction < 0.0:
        raise ValueError("minimum_thickness_neighbor_fraction must be >= 0")
    if not np.isfinite(controls.sensitivity_update_multiplier):
        raise ValueError("sensitivity_update_multiplier must be finite")
    if abs(float(controls.sensitivity_update_multiplier)) <= 1.0e-12:
        raise ValueError("sensitivity_update_multiplier must be nonzero")
    if controls.sensitivity_derivative_multiplier is not None and not np.isfinite(controls.sensitivity_derivative_multiplier):
        raise ValueError("sensitivity_derivative_multiplier must be finite")
    if not np.isfinite(controls.constraint_sensitivity_weight):
        raise ValueError("constraint_sensitivity_weight must be finite")
    if controls.constraint_sensitivity_weight < 0.0:
        raise ValueError("constraint_sensitivity_weight must be >= 0")


def _assert_compatible_grid(density_state: DensityStateData, bundle: FieldBundle) -> None:
    if density_state.grid.shape != bundle.grid.shape:
        raise ValueError(f"Density grid shape {density_state.grid.shape} does not match source SDF grid {bundle.grid.shape}")
    if not np.allclose(density_state.grid.origin, bundle.grid.origin):
        raise ValueError("Density grid origin does not match source SDF grid origin")
    if not np.isclose(density_state.grid.spacing, bundle.grid.spacing):
        raise ValueError("Density grid spacing does not match source SDF grid spacing")


def _write_history(path: Path, steps: list[DensityStepResult]) -> None:
    fieldnames = [
        "index",
        "status",
        "objective",
        "penalty",
        "constraints_ok",
        "rejection_reasons",
        "drag_coefficient",
        "downforce_coefficient",
        "front_downforce_ratio",
        "efficiency",
        "efficiency_constraint",
        "solid_fraction",
        "volume_fraction",
        "density_delta_min",
        "density_delta_max",
        "density_delta_l2",
        "root_anchor_cell_count",
        "thin_cell_penalty_count",
        "step_dir",
        "output_design_state_json",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for step in steps:
            writer.writerow(
                {
                    "index": step.index,
                    "status": step.status,
                    "objective": step.objective,
                    "penalty": step.penalty,
                    "constraints_ok": step.constraints_ok,
                    "rejection_reasons": ";".join(step.rejection_reasons),
                    "drag_coefficient": step.drag_coefficient,
                    "downforce_coefficient": step.downforce_coefficient,
                    "front_downforce_ratio": step.front_downforce_ratio,
                    "efficiency": step.efficiency,
                    "efficiency_constraint": step.efficiency_constraint,
                    "solid_fraction": step.solid_fraction,
                    "volume_fraction": step.volume_fraction,
                    "density_delta_min": step.density_delta_min,
                    "density_delta_max": step.density_delta_max,
                    "density_delta_l2": step.density_delta_l2,
                    "root_anchor_cell_count": step.root_anchor_cell_count,
                    "thin_cell_penalty_count": step.thin_cell_penalty_count,
                    "step_dir": step.step_dir,
                    "output_design_state_json": step.output_design_state_json,
                }
            )


def _select_best(steps: list[DensityStepResult]) -> DensityStepResult:
    accepted = [step for step in steps if step.status == "accepted"]
    best_pool = accepted or steps
    return min(best_pool, key=lambda step: step.objective)


def _promote_best(run_dir: Path, best: DensityStepResult) -> None:
    best_dir = run_dir / "best_design"
    if best_dir.exists():
        shutil.rmtree(best_dir)
    shutil.copytree(best.step_dir, best_dir)


def _step_result_from_dict(data: dict[str, object]) -> DensityStepResult:
    return DensityStepResult(
        index=int(data["index"]),
        step_dir=Path(str(data["step_dir"])),
        input_design_state_json=Path(str(data["input_design_state_json"])),
        output_design_state_json=Path(str(data["output_design_state_json"])),
        project_yaml=Path(str(data["project_yaml"])),
        sensitivity_vti=Path(str(data["sensitivity_vti"])),
        sensitivity_summary_json=Path(str(data["sensitivity_summary_json"])),
        density_update_vti=Path(str(data["density_update_vti"])),
        density_vti=Path(str(data["density_vti"])),
        density_stl=Path(str(data["density_stl"])),
        controls=dict(data["controls"]),
        status=str(data["status"]),
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
        objective=float(data["objective"]),
        penalty=float(data["penalty"]),
        drag_coefficient=float(data["drag_coefficient"]),
        downforce_coefficient=float(data["downforce_coefficient"]),
        front_downforce_coefficient=float(data["front_downforce_coefficient"]),
        rear_downforce_coefficient=float(data["rear_downforce_coefficient"]),
        front_downforce_ratio=float(data["front_downforce_ratio"]),
        efficiency=float(data["efficiency"]),
        efficiency_constraint=float(data["efficiency_constraint"]),
        solid_fraction=float(data["solid_fraction"]),
        volume_fraction=float(data["volume_fraction"]),
        active_cell_count=int(data["active_cell_count"]),
        density_delta_min=float(data["density_delta_min"]),
        density_delta_max=float(data["density_delta_max"]),
        density_delta_l2=float(data["density_delta_l2"]),
        root_anchor_cell_count=int(data["root_anchor_cell_count"]),
        thin_cell_penalty_count=int(data["thin_cell_penalty_count"]),
    )
