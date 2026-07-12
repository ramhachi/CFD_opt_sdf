from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from .fixed_grid_contract import (
    FIXED_GRID_CONTRACT_SCHEMA_VERSION,
    _assert_same_grid,
    _read_cell_vti,
    _write_cell_vti,
)
from .fixed_grid_primal import load_fixed_grid_density_state


FIXED_GRID_OPTIMIZER_SCHEMA_VERSION = 1
OPTIMIZER_BACKENDS = (
    "projected-gradient",
    "slsqp-linearized",
)


@dataclass(frozen=True)
class FixedGridOptimizerControls:
    optimizer_backend: str = "projected-gradient"
    move_limit: float = 0.03
    density_lower: float = 0.0
    density_upper: float = 1.0
    volume_fraction_min: float = 0.05
    volume_fraction_max: float = 0.55
    efficiency_constraint_limit: float = 0.0
    connectivity_nominal_limit: float | None = None
    connectivity_eroded_limit: float | None = None
    enforce_efficiency: bool = True
    enforce_connectivity: bool = True
    enforce_volume: bool = True
    allow_sampled_connectivity_derivatives: bool = False
    max_projection_iterations: int = 40
    linearized_tolerance: float = 1.0e-8
    subproblem_regularization: float = 1.0
    max_optimizer_iterations: int = 200
    optimizer_ftol: float = 1.0e-9

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FixedGridConstrainedStepArtifacts:
    output_dir: Path
    input_topology_state_json: Path
    output_topology_state_json: Path
    input_density_vti: Path
    output_density_vti: Path
    sensitivity_vti: Path
    update_vti: Path
    summary_json: Path
    summary: dict[str, object]

    @property
    def ok(self) -> bool:
        return bool(self.summary.get("ok"))

    @property
    def accepted_by_linearization(self) -> bool:
        return bool(self.summary.get("accepted_by_linearization"))

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in (
            "output_dir",
            "input_topology_state_json",
            "output_topology_state_json",
            "input_density_vti",
            "output_density_vti",
            "sensitivity_vti",
            "update_vti",
            "summary_json",
        ):
            data[key] = str(data[key])
        return data


@dataclass(frozen=True)
class _LinearConstraint:
    name: str
    value: float
    limit: float
    gradient: np.ndarray
    enforced: bool = True

    @property
    def residual(self) -> float:
        return float(self.value - self.limit)


@dataclass(frozen=True)
class _OptimizerBackendResult:
    delta: np.ndarray
    raw_delta: np.ndarray
    history: list[dict[str, object]]
    metadata: dict[str, object]


def run_fixed_grid_constrained_density_step(
    topology_state_json: Path,
    *,
    sensitivity_vti: Path,
    output_dir: Path,
    controls: FixedGridOptimizerControls | None = None,
    sensitivity_summary_json: Path | None = None,
    primal_summary_json: Path | None = None,
    connectivity_summary_json: Path | None = None,
) -> FixedGridConstrainedStepArtifacts:
    controls = controls or FixedGridOptimizerControls()
    _validate_controls(controls)

    density_state = load_fixed_grid_density_state(topology_state_json)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sensitivity_vti = sensitivity_vti.resolve()
    sensitivity_grid, sensitivity_arrays = _read_cell_vti(
        sensitivity_vti,
        expected_kind="fixed_grid_sensitivity",
    )
    _assert_same_grid(
        sensitivity_grid,
        density_state.grid,
        "fixed_grid_sensitivity.vti",
        "density.vti",
    )
    _validate_sensitivity_arrays(density_state.arrays, sensitivity_arrays)

    sensitivity_summary = _read_optional_json(
        _resolve_summary_path(sensitivity_vti, sensitivity_summary_json)
    )
    primal_summary = _read_optional_json(
        _resolve_primal_summary_path(primal_summary_json, sensitivity_summary)
    )
    connectivity_summary = _read_optional_json(connectivity_summary_json)

    density = np.asarray(density_state.arrays["rho"], dtype=np.float64)
    active = np.asarray(density_state.arrays["active_design_mask"], dtype=np.uint8) > 0
    allowed = np.asarray(density_state.arrays["allowed_mask"], dtype=np.uint8) > 0
    forbidden = np.asarray(density_state.arrays["forbidden_mask"], dtype=np.uint8) > 0
    fixed_solid = np.asarray(density_state.arrays["fixed_solid_mask"], dtype=np.uint8) > 0
    root_mask = np.asarray(density_state.arrays["root_mask"], dtype=np.uint8) > 0
    active &= allowed & ~forbidden & ~fixed_solid

    objective_gradient = -np.asarray(
        sensitivity_arrays["d_downforce_d_rho"],
        dtype=np.float64,
    )
    objective_gradient[~active] = 0.0
    constraints = _build_constraints(
        density=density,
        active=active,
        sensitivity_arrays=sensitivity_arrays,
        controls=controls,
        sensitivity_summary=sensitivity_summary,
        primal_summary=primal_summary,
        connectivity_summary=connectivity_summary,
    )
    _check_connectivity_derivative_readiness(
        sensitivity_arrays,
        density_state.arrays,
        active=active,
        controls=controls,
        sensitivity_summary=sensitivity_summary,
        constraints=constraints,
    )

    lower_delta = np.maximum(controls.density_lower - density, -controls.move_limit)
    upper_delta = np.minimum(controls.density_upper - density, controls.move_limit)
    lower_delta[~active] = 0.0
    upper_delta[~active] = 0.0
    backend_result = _solve_optimizer_backend(
        objective_gradient,
        constraints,
        active=active,
        lower_delta=lower_delta,
        upper_delta=upper_delta,
        controls=controls,
    )
    candidate_density = _apply_hard_masks(
        density + backend_result.delta,
        density_state.arrays,
        lower=controls.density_lower,
        upper=controls.density_upper,
    )
    actual_delta = candidate_density - density
    prediction = _linearized_prediction(
        constraints,
        actual_delta,
        tolerance=controls.linearized_tolerance,
    )
    accepted_by_linearization = bool(
        all(item["satisfied"] for item in prediction["constraints"])
    )

    output_density_vti = output_dir / "density.vti"
    output_arrays = _updated_density_arrays(
        density_state.arrays,
        candidate_density,
    )
    _write_cell_vti(
        density_state.grid,
        output_arrays,
        output_density_vti,
        kind="fixed_grid_density",
    )

    update_vti = output_dir / "fixed_grid_constrained_update.vti"
    _write_cell_vti(
        density_state.grid,
        {
            "rho_old": density.astype(np.float32),
            "rho_candidate": candidate_density.astype(np.float32),
            "rho_delta": actual_delta.astype(np.float32),
            "objective_gradient": objective_gradient.astype(np.float32),
            "d_efficiency_constraint_d_rho": np.asarray(
                sensitivity_arrays["d_efficiency_constraint_d_rho"],
                dtype=np.float32,
            ),
            "d_connectivity_nominal_d_rho": np.asarray(
                sensitivity_arrays["d_connectivity_nominal_d_rho"],
                dtype=np.float32,
            ),
            "d_connectivity_eroded_d_rho": np.asarray(
                sensitivity_arrays["d_connectivity_eroded_d_rho"],
                dtype=np.float32,
            ),
            "active_design_mask": active.astype(np.uint8),
        },
        update_vti,
        kind="fixed_grid_constrained_update",
    )

    output_topology_state_json = output_dir / "topology_state.json"
    output_state = _updated_topology_state(
        density_state.state,
        parent_topology_state_json=density_state.topology_state_json,
        density_vti=output_density_vti,
        sensitivity_vti=sensitivity_vti,
        update_vti=update_vti,
        optimizer_backend=controls.optimizer_backend,
    )
    output_topology_state_json.write_text(
        json.dumps(output_state, indent=2),
        encoding="utf-8",
    )

    objective_prediction = {
        "base_objective": _optional_float(primal_summary.get("objective")),
        "linearized_delta": float(np.dot(objective_gradient, actual_delta)),
    }
    if objective_prediction["base_objective"] is not None:
        objective_prediction["predicted_objective"] = float(
            objective_prediction["base_objective"]
            + objective_prediction["linearized_delta"]
        )

    active_delta = actual_delta[active]
    summary = {
        "schema_version": FIXED_GRID_OPTIMIZER_SCHEMA_VERSION,
        "kind": "fixed_grid_constrained_step_summary",
        "roadmap": "Generic Aerodynamic Topology Optimization",
        "roadmap_phase": "T5",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "linearized_accept" if accepted_by_linearization else "linearized_reject",
        "ok": True,
        "accepted_by_linearization": accepted_by_linearization,
        "optimizer_backend": backend_result.metadata,
        "controls": controls.to_dict(),
        "input_topology_state_json": str(density_state.topology_state_json),
        "output_topology_state_json": str(output_topology_state_json),
        "input_density_vti": str(density_state.density_vti),
        "output_density_vti": str(output_density_vti),
        "sensitivity_vti": str(sensitivity_vti),
        "sensitivity_summary_json": (
            str(_resolve_summary_path(sensitivity_vti, sensitivity_summary_json))
            if _resolve_summary_path(sensitivity_vti, sensitivity_summary_json)
            else None
        ),
        "primal_summary_json": (
            str(_resolve_primal_summary_path(primal_summary_json, sensitivity_summary))
            if _resolve_primal_summary_path(primal_summary_json, sensitivity_summary)
            else None
        ),
        "connectivity_summary_json": (
            str(connectivity_summary_json.resolve()) if connectivity_summary_json else None
        ),
        "objective": objective_prediction,
        "linearized_constraints": prediction["constraints"],
        "linearized_constraints_ok": accepted_by_linearization,
        "optimizer_history": backend_result.history,
        "counts": {
            "active_design_cells": int(np.count_nonzero(active)),
            "allowed_cells": int(np.count_nonzero(allowed)),
            "fixed_solid_cells": int(np.count_nonzero(fixed_solid)),
            "root_cells": int(np.count_nonzero(root_mask)),
        },
        "density_statistics": {
            "rho_old_active": _array_stats(density[active]),
            "rho_candidate_active": _array_stats(candidate_density[active]),
            "rho_delta_active": _array_stats(active_delta),
            "volume_fraction_old": _volume_fraction(density, active),
            "volume_fraction_candidate": _volume_fraction(candidate_density, active),
        },
        "artifacts": {
            "update_vti": str(update_vti),
            "density_vti": str(output_density_vti),
            "topology_state_json": str(output_topology_state_json),
        },
    }
    summary_json = output_dir / "fixed_grid_constrained_step_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return FixedGridConstrainedStepArtifacts(
        output_dir=output_dir,
        input_topology_state_json=density_state.topology_state_json,
        output_topology_state_json=output_topology_state_json,
        input_density_vti=density_state.density_vti,
        output_density_vti=output_density_vti,
        sensitivity_vti=sensitivity_vti,
        update_vti=update_vti,
        summary_json=summary_json,
        summary=summary,
    )


def _build_constraints(
    *,
    density: np.ndarray,
    active: np.ndarray,
    sensitivity_arrays: dict[str, np.ndarray],
    controls: FixedGridOptimizerControls,
    sensitivity_summary: dict[str, object],
    primal_summary: dict[str, object],
    connectivity_summary: dict[str, object],
) -> list[_LinearConstraint]:
    constraints: list[_LinearConstraint] = []
    if controls.enforce_efficiency:
        efficiency_value = _resolve_efficiency_constraint(
            primal_summary,
            sensitivity_summary,
        )
        constraints.append(
            _constraint(
                "efficiency",
                value=efficiency_value,
                limit=controls.efficiency_constraint_limit,
                gradient=np.asarray(
                    sensitivity_arrays["d_efficiency_constraint_d_rho"],
                    dtype=np.float64,
                ),
                active=active,
            )
        )

    if controls.enforce_connectivity:
        nominal_value = _resolve_connectivity_objective(
            "nominal",
            sensitivity_summary,
            connectivity_summary,
        )
        eroded_value = _resolve_connectivity_objective(
            "eroded",
            sensitivity_summary,
            connectivity_summary,
        )
        nominal_limit = (
            float(controls.connectivity_nominal_limit)
            if controls.connectivity_nominal_limit is not None
            else nominal_value
        )
        eroded_limit = (
            float(controls.connectivity_eroded_limit)
            if controls.connectivity_eroded_limit is not None
            else eroded_value
        )
        constraints.extend(
            [
                _constraint(
                    "connectivity_nominal",
                    value=nominal_value,
                    limit=nominal_limit,
                    gradient=np.asarray(
                        sensitivity_arrays["d_connectivity_nominal_d_rho"],
                        dtype=np.float64,
                    ),
                    active=active,
                ),
                _constraint(
                    "connectivity_eroded",
                    value=eroded_value,
                    limit=eroded_limit,
                    gradient=np.asarray(
                        sensitivity_arrays["d_connectivity_eroded_d_rho"],
                        dtype=np.float64,
                    ),
                    active=active,
                ),
            ]
        )

    if controls.enforce_volume:
        active_count = max(int(np.count_nonzero(active)), 1)
        mean_density = _volume_fraction(density, active)
        volume_gradient = np.zeros(density.size, dtype=np.float64)
        volume_gradient[active] = 1.0 / float(active_count)
        constraints.extend(
            [
                _constraint(
                    "volume_fraction_max",
                    value=mean_density,
                    limit=controls.volume_fraction_max,
                    gradient=volume_gradient,
                    active=active,
                ),
                _constraint(
                    "volume_fraction_min",
                    value=controls.volume_fraction_min,
                    limit=mean_density,
                    gradient=-volume_gradient,
                    active=active,
                ),
            ]
        )
    return constraints


def _constraint(
    name: str,
    *,
    value: float,
    limit: float,
    gradient: np.ndarray,
    active: np.ndarray,
) -> _LinearConstraint:
    grad = np.asarray(gradient, dtype=np.float64).copy()
    if grad.shape != active.shape:
        raise ValueError(f"{name} gradient shape {grad.shape} does not match density")
    grad[~active] = 0.0
    if not np.isfinite(grad).all():
        raise ValueError(f"{name} gradient contains non-finite values")
    return _LinearConstraint(
        name=name,
        value=float(value),
        limit=float(limit),
        gradient=grad,
    )


def _check_connectivity_derivative_readiness(
    sensitivity_arrays: dict[str, np.ndarray],
    density_arrays: dict[str, np.ndarray],
    *,
    active: np.ndarray,
    controls: FixedGridOptimizerControls,
    sensitivity_summary: dict[str, object],
    constraints: list[_LinearConstraint],
) -> None:
    if not controls.enforce_connectivity:
        return
    status = str(sensitivity_summary.get("connectivity_derivative_status", ""))
    if (
        "sampled" in status
        and not controls.allow_sampled_connectivity_derivatives
    ):
        raise ValueError(
            "sampled connectivity derivatives are diagnostic only; pass "
            "allow_sampled_connectivity_derivatives=True for an explicit "
            "diagnostic step"
        )
    sample_mask = sensitivity_arrays.get("connectivity_derivative_sample_mask")
    if sample_mask is not None and not controls.allow_sampled_connectivity_derivatives:
        root = np.asarray(density_arrays["root_mask"], dtype=np.uint8) > 0
        fixed = np.asarray(density_arrays["fixed_solid_mask"], dtype=np.uint8) > 0
        candidates = active & ~root & ~fixed
        sampled = np.asarray(sample_mask, dtype=np.uint8) > 0
        if np.any(candidates & ~sampled):
            raise ValueError(
                "connectivity_derivative_sample_mask does not cover every "
                "candidate active cell"
            )
    for constraint in constraints:
        if not constraint.name.startswith("connectivity"):
            continue
        norm = float(np.linalg.norm(constraint.gradient[active]))
        if norm <= 1.0e-30:
            raise ValueError(f"{constraint.name} derivative is zero on active cells")


def _initial_objective_delta(
    objective_gradient: np.ndarray,
    *,
    active: np.ndarray,
    controls: FixedGridOptimizerControls,
) -> np.ndarray:
    delta = np.zeros_like(objective_gradient, dtype=np.float64)
    active_grad = objective_gradient[active]
    scale = float(np.max(np.abs(active_grad))) if active_grad.size else 0.0
    if scale <= 1.0e-30:
        return delta
    delta[active] = -controls.move_limit * active_grad / scale
    return delta


def _solve_optimizer_backend(
    objective_gradient: np.ndarray,
    constraints: list[_LinearConstraint],
    *,
    active: np.ndarray,
    lower_delta: np.ndarray,
    upper_delta: np.ndarray,
    controls: FixedGridOptimizerControls,
) -> _OptimizerBackendResult:
    if controls.optimizer_backend == "projected-gradient":
        return _solve_projected_gradient_backend(
            objective_gradient,
            constraints,
            active=active,
            lower_delta=lower_delta,
            upper_delta=upper_delta,
            controls=controls,
        )
    if controls.optimizer_backend == "slsqp-linearized":
        return _solve_slsqp_linearized_backend(
            objective_gradient,
            constraints,
            active=active,
            lower_delta=lower_delta,
            upper_delta=upper_delta,
            controls=controls,
        )
    raise ValueError(f"Unsupported optimizer_backend: {controls.optimizer_backend!r}")


def _solve_projected_gradient_backend(
    objective_gradient: np.ndarray,
    constraints: list[_LinearConstraint],
    *,
    active: np.ndarray,
    lower_delta: np.ndarray,
    upper_delta: np.ndarray,
    controls: FixedGridOptimizerControls,
) -> _OptimizerBackendResult:
    raw_delta = _initial_objective_delta(
        objective_gradient,
        active=active,
        controls=controls,
    )
    delta, history = _project_delta_to_linearized_constraints(
        raw_delta,
        constraints,
        active=active,
        lower_delta=lower_delta,
        upper_delta=upper_delta,
        max_iterations=controls.max_projection_iterations,
        tolerance=controls.linearized_tolerance,
    )
    return _OptimizerBackendResult(
        delta=delta,
        raw_delta=raw_delta,
        history=history,
        metadata={
            "name": "projected-gradient",
            "solver": "linearized_projected_gradient",
            "role": "GCMMA-compatible adapter smoke backend",
            "production_gcmma": False,
            "note": (
                "This backend enforces the same scalar constraint contract a "
                "GCMMA implementation will consume. It is a conservative T5 "
                "integration step, not a production GCMMA solver."
            ),
        },
    )


def _solve_slsqp_linearized_backend(
    objective_gradient: np.ndarray,
    constraints: list[_LinearConstraint],
    *,
    active: np.ndarray,
    lower_delta: np.ndarray,
    upper_delta: np.ndarray,
    controls: FixedGridOptimizerControls,
) -> _OptimizerBackendResult:
    active_indices = np.flatnonzero(active)
    raw_delta = _initial_objective_delta(
        objective_gradient,
        active=active,
        controls=controls,
    )
    if active_indices.size == 0:
        return _OptimizerBackendResult(
            delta=np.zeros_like(objective_gradient, dtype=np.float64),
            raw_delta=raw_delta,
            history=[],
            metadata={
                "name": "slsqp-linearized",
                "solver": "scipy.optimize.minimize/SLSQP",
                "status": "no_active_cells",
                "success": True,
                "production_gcmma": False,
            },
        )

    initial_delta, initial_history = _project_delta_to_linearized_constraints(
        raw_delta,
        constraints,
        active=active,
        lower_delta=lower_delta,
        upper_delta=upper_delta,
        max_iterations=controls.max_projection_iterations,
        tolerance=controls.linearized_tolerance,
    )
    feasibility = _linearized_move_bound_feasibility(
        constraints,
        lower_delta=lower_delta,
        upper_delta=upper_delta,
        tolerance=controls.linearized_tolerance,
    )
    impossible = [
        item
        for item in feasibility
        if not item["feasible_with_move_bounds"]
    ]
    if impossible:
        history = list(initial_history)
        history.append(
            {
                "iteration": 0,
                "max_linearized_violation": _max_linearized_violation(
                    constraints,
                    initial_delta,
                ),
                "adjusted_constraints": None,
                "backend": "slsqp-linearized",
                "success": False,
                "message": "linearized constraints infeasible within move bounds",
                "impossible_constraints": [str(item["name"]) for item in impossible],
            }
        )
        return _OptimizerBackendResult(
            delta=initial_delta,
            raw_delta=raw_delta,
            history=history,
            metadata={
                "name": "slsqp-linearized",
                "solver": "scipy.optimize.minimize/SLSQP",
                "role": "linearized constrained subproblem backend",
                "production_gcmma": False,
                "success": False,
                "status": "infeasible_move_bounds",
                "message": "linearized constraints are infeasible within move bounds",
                "iterations": 0,
                "subproblem_objective": None,
                "max_linearized_violation": _max_linearized_violation(
                    constraints,
                    initial_delta,
                ),
                "feasibility": feasibility,
                "note": (
                    "SLSQP was skipped because at least one linearized "
                    "constraint cannot be satisfied within the current move "
                    "bounds."
                ),
            },
        )
    x0 = initial_delta[active_indices]
    objective_active = np.asarray(objective_gradient[active_indices], dtype=np.float64)
    objective_scale = float(np.max(np.abs(objective_active))) if objective_active.size else 0.0
    if objective_scale <= 1.0e-30:
        scaled_gradient = np.zeros_like(objective_active)
    else:
        scaled_gradient = objective_active / objective_scale
    proximal_weight = controls.subproblem_regularization / max(
        controls.move_limit,
        1.0e-12,
    )

    def objective(x: np.ndarray) -> float:
        values = np.asarray(x, dtype=np.float64)
        return float(
            np.dot(scaled_gradient, values)
            + 0.5 * proximal_weight * np.dot(values, values)
        )

    def jacobian(x: np.ndarray) -> np.ndarray:
        values = np.asarray(x, dtype=np.float64)
        return scaled_gradient + proximal_weight * values

    scipy_constraints = []
    for constraint in constraints:
        gradient = np.asarray(constraint.gradient[active_indices], dtype=np.float64)

        def fun(x: np.ndarray, *, c: _LinearConstraint = constraint, g: np.ndarray = gradient) -> float:
            return float(-(c.residual + np.dot(g, x)))

        def jac(x: np.ndarray, *, g: np.ndarray = gradient) -> np.ndarray:
            return -g

        scipy_constraints.append({"type": "ineq", "fun": fun, "jac": jac})

    result = minimize(
        objective,
        x0,
        method="SLSQP",
        jac=jacobian,
        bounds=[
            (float(lower_delta[index]), float(upper_delta[index]))
            for index in active_indices
        ],
        constraints=scipy_constraints,
        options={
            "maxiter": controls.max_optimizer_iterations,
            "ftol": controls.optimizer_ftol,
            "disp": False,
        },
    )
    x = np.asarray(result.x if result.x is not None else x0, dtype=np.float64)
    delta = np.zeros_like(objective_gradient, dtype=np.float64)
    delta[active_indices] = x
    delta = np.clip(delta, lower_delta, upper_delta)
    delta[~active] = 0.0
    max_violation = _max_linearized_violation(constraints, delta)
    history = list(initial_history)
    history.append(
        {
            "iteration": int(getattr(result, "nit", 0)),
            "max_linearized_violation": max_violation,
            "adjusted_constraints": None,
            "backend": "slsqp-linearized",
            "success": bool(result.success),
            "message": str(result.message),
            "subproblem_objective": float(result.fun) if np.isfinite(result.fun) else None,
        }
    )
    return _OptimizerBackendResult(
        delta=delta,
        raw_delta=raw_delta,
        history=history,
        metadata={
            "name": "slsqp-linearized",
            "solver": "scipy.optimize.minimize/SLSQP",
            "role": "linearized constrained subproblem backend",
            "production_gcmma": False,
            "success": bool(result.success),
            "status": int(result.status),
            "message": str(result.message),
            "iterations": int(getattr(result, "nit", 0)),
            "subproblem_objective": float(result.fun) if np.isfinite(result.fun) else None,
            "max_linearized_violation": max_violation,
            "feasibility": feasibility,
            "note": (
                "This backend solves the current linearized T5 subproblem with "
                "SLSQP. It fixes the GCMMA value/gradient interface but is not "
                "a production GCMMA implementation."
            ),
        },
    )


def _project_delta_to_linearized_constraints(
    delta: np.ndarray,
    constraints: list[_LinearConstraint],
    *,
    active: np.ndarray,
    lower_delta: np.ndarray,
    upper_delta: np.ndarray,
    max_iterations: int,
    tolerance: float,
) -> tuple[np.ndarray, list[dict[str, object]]]:
    result = np.clip(delta, lower_delta, upper_delta)
    result[~active] = 0.0
    history: list[dict[str, object]] = []
    for iteration in range(max_iterations):
        max_violation = 0.0
        adjusted = 0
        for constraint in constraints:
            violation = constraint.residual + float(np.dot(constraint.gradient, result))
            max_violation = max(max_violation, violation)
            if violation <= tolerance:
                continue
            grad = constraint.gradient.copy()
            grad[~active] = 0.0
            norm_sq = float(np.dot(grad, grad))
            if norm_sq <= 1.0e-30:
                continue
            result = result - (violation / norm_sq) * grad
            result = np.clip(result, lower_delta, upper_delta)
            result[~active] = 0.0
            adjusted += 1
        history.append(
            {
                "iteration": iteration,
                "max_linearized_violation": float(max_violation),
                "adjusted_constraints": adjusted,
            }
        )
        if max_violation <= tolerance or adjusted == 0:
            break
    return result, history


def _max_linearized_violation(
    constraints: list[_LinearConstraint],
    delta: np.ndarray,
) -> float:
    if not constraints:
        return 0.0
    return float(
        max(
            constraint.residual + float(np.dot(constraint.gradient, delta))
            for constraint in constraints
        )
    )


def _linearized_move_bound_feasibility(
    constraints: list[_LinearConstraint],
    *,
    lower_delta: np.ndarray,
    upper_delta: np.ndarray,
    tolerance: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for constraint in constraints:
        gradient = np.asarray(constraint.gradient, dtype=np.float64)
        best_delta = np.where(gradient >= 0.0, lower_delta, upper_delta)
        minimum_change = float(np.dot(gradient, best_delta))
        minimum_predicted_violation = constraint.residual + minimum_change
        rows.append(
            {
                "name": constraint.name,
                "current_residual": constraint.residual,
                "minimum_linearized_change": minimum_change,
                "minimum_predicted_violation": minimum_predicted_violation,
                "feasible_with_move_bounds": bool(
                    minimum_predicted_violation <= tolerance
                ),
            }
        )
    return rows


def _linearized_prediction(
    constraints: list[_LinearConstraint],
    delta: np.ndarray,
    *,
    tolerance: float,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for constraint in constraints:
        change = float(np.dot(constraint.gradient, delta))
        predicted = constraint.value + change
        violation = predicted - constraint.limit
        rows.append(
            {
                "name": constraint.name,
                "value": constraint.value,
                "limit": constraint.limit,
                "residual": constraint.residual,
                "linearized_change": change,
                "predicted_value": predicted,
                "predicted_violation": violation,
                "satisfied": bool(violation <= tolerance),
            }
        )
    return {"constraints": rows}


def _updated_density_arrays(
    arrays: dict[str, np.ndarray],
    density: np.ndarray,
) -> dict[str, np.ndarray]:
    beta_max = _infer_beta_max(arrays)
    rho = np.asarray(density, dtype=np.float32)
    result = {
        "rho": rho,
        "rho_filtered": rho.copy(),
        "rho_projected": rho.copy(),
        "alpha": (beta_max * rho).astype(np.float32),
        "allowed_mask": np.asarray(arrays["allowed_mask"], dtype=np.uint8),
        "forbidden_mask": np.asarray(arrays["forbidden_mask"], dtype=np.uint8),
        "fixed_solid_mask": np.asarray(arrays["fixed_solid_mask"], dtype=np.uint8),
        "root_mask": np.asarray(arrays["root_mask"], dtype=np.uint8),
        "active_design_mask": np.asarray(arrays["active_design_mask"], dtype=np.uint8),
    }
    return result


def _updated_topology_state(
    state: dict[str, object],
    *,
    parent_topology_state_json: Path,
    density_vti: Path,
    sensitivity_vti: Path,
    update_vti: Path,
    optimizer_backend: str,
) -> dict[str, object]:
    output = json.loads(json.dumps(state))
    output["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    output["density_vti"] = density_vti.name
    output["source_solver"] = {
        **dict(output.get("source_solver") or {}),
        "backend": "fixed-grid-constrained-density-step",
        "solver": optimizer_backend,
        "parent_topology_state_json": str(parent_topology_state_json),
        "sensitivity_vti": str(sensitivity_vti),
        "update_vti": str(update_vti),
        "mesh_policy": "fixed",
        "remeshing_per_iteration": False,
    }
    return output


def _apply_hard_masks(
    density: np.ndarray,
    arrays: dict[str, np.ndarray],
    *,
    lower: float,
    upper: float,
) -> np.ndarray:
    values = np.clip(np.asarray(density, dtype=np.float64), lower, upper)
    allowed = np.asarray(arrays["allowed_mask"], dtype=np.uint8) > 0
    forbidden = np.asarray(arrays["forbidden_mask"], dtype=np.uint8) > 0
    fixed = np.asarray(arrays["fixed_solid_mask"], dtype=np.uint8) > 0
    values[(~allowed) & (~fixed)] = 0.0
    values[fixed & (~forbidden)] = 1.0
    values[forbidden] = 0.0
    return np.clip(values, lower, upper)


def _validate_sensitivity_arrays(
    density_arrays: dict[str, np.ndarray],
    sensitivity_arrays: dict[str, np.ndarray],
) -> None:
    required = {
        "d_downforce_d_rho",
        "d_drag_d_rho",
        "d_efficiency_constraint_d_rho",
        "d_connectivity_nominal_d_rho",
        "d_connectivity_eroded_d_rho",
        "active_design_mask",
    }
    missing = sorted(required - set(sensitivity_arrays))
    if missing:
        raise ValueError(f"fixed_grid_sensitivity.vti is missing arrays: {', '.join(missing)}")
    density_active = np.asarray(density_arrays["active_design_mask"], dtype=np.uint8)
    sensitivity_active = np.asarray(
        sensitivity_arrays["active_design_mask"],
        dtype=np.uint8,
    )
    if not np.array_equal(density_active, sensitivity_active):
        raise ValueError("density and sensitivity active_design_mask arrays do not match")
    inactive = sensitivity_active == 0
    for name in required - {"active_design_mask"}:
        values = np.asarray(sensitivity_arrays[name], dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError(f"{name} contains non-finite values")
        if np.any(np.abs(values[inactive]) > 1.0e-6):
            raise ValueError(f"{name} must be zero outside active_design_mask")


def _resolve_efficiency_constraint(
    primal_summary: dict[str, object],
    sensitivity_summary: dict[str, object],
) -> float:
    value = primal_summary.get("efficiency_constraint")
    if value is not None:
        return float(value)
    primal_values = sensitivity_summary.get("primal_values")
    if isinstance(primal_values, dict) and primal_values.get("efficiency_constraint") is not None:
        return float(primal_values["efficiency_constraint"])
    raise ValueError("efficiency constraint value is required for T5")


def _resolve_connectivity_objective(
    which: str,
    sensitivity_summary: dict[str, object],
    connectivity_summary: dict[str, object],
) -> float:
    key = f"connectivity_{which}_violation_l1"
    objectives = sensitivity_summary.get("base_objectives")
    if isinstance(objectives, dict) and objectives.get(key) is not None:
        return float(objectives[key])
    block = connectivity_summary.get(which)
    if isinstance(block, dict) and block.get("violation_l1") is not None:
        return float(block["violation_l1"])
    raise ValueError(f"{which} connectivity objective value is required for T5")


def _resolve_summary_path(
    sensitivity_vti: Path,
    explicit: Path | None,
) -> Path | None:
    if explicit is not None:
        return explicit.resolve()
    candidate = sensitivity_vti.with_name("fixed_grid_sensitivity_summary.json")
    return candidate if candidate.exists() else None


def _resolve_primal_summary_path(
    explicit: Path | None,
    sensitivity_summary: dict[str, object],
) -> Path | None:
    if explicit is not None:
        return explicit.resolve()
    value = sensitivity_summary.get("primal_summary_json")
    if value:
        path = Path(str(value))
        return path if path.is_absolute() else Path.cwd() / path
    return None


def _read_optional_json(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _infer_beta_max(arrays: dict[str, np.ndarray]) -> float:
    projected = np.asarray(arrays.get("rho_projected"), dtype=np.float64)
    alpha = np.asarray(arrays.get("alpha"), dtype=np.float64)
    if projected.shape == alpha.shape:
        mask = np.abs(projected) > 1.0e-12
        ratios = alpha[mask] / projected[mask] if np.any(mask) else np.array([])
        ratios = ratios[np.isfinite(ratios) & (ratios > 0.0)]
        if ratios.size:
            return float(np.median(ratios))
    return 2500.0


def _volume_fraction(density: np.ndarray, active: np.ndarray) -> float:
    values = density[active]
    return float(np.mean(values)) if values.size else 0.0


def _array_stats(values: np.ndarray) -> dict[str, object]:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        return {"min": None, "max": None, "mean": None, "l2": 0.0, "count": 0}
    return {
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "mean": float(np.mean(array)),
        "l2": float(np.linalg.norm(array)),
        "count": int(array.size),
    }


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _validate_controls(controls: FixedGridOptimizerControls) -> None:
    if controls.optimizer_backend not in OPTIMIZER_BACKENDS:
        raise ValueError(
            "optimizer_backend must be one of: "
            + ", ".join(OPTIMIZER_BACKENDS)
        )
    if controls.move_limit < 0.0:
        raise ValueError("move_limit must be >= 0")
    if controls.density_lower > controls.density_upper:
        raise ValueError("density_lower must be <= density_upper")
    if not 0.0 <= controls.volume_fraction_min <= controls.volume_fraction_max <= 1.0:
        raise ValueError("volume fraction bounds must satisfy 0 <= min <= max <= 1")
    if controls.max_projection_iterations < 0:
        raise ValueError("max_projection_iterations must be >= 0")
    if controls.linearized_tolerance < 0.0:
        raise ValueError("linearized_tolerance must be >= 0")
    if controls.subproblem_regularization <= 0.0:
        raise ValueError("subproblem_regularization must be > 0")
    if controls.max_optimizer_iterations < 1:
        raise ValueError("max_optimizer_iterations must be >= 1")
    if controls.optimizer_ftol <= 0.0:
        raise ValueError("optimizer_ftol must be > 0")


def copy_optimizer_step_artifacts(source_dir: Path, target_dir: Path) -> None:
    """Utility used by future resumable T5 runners."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "density.vti",
        "topology_state.json",
        "fixed_grid_constrained_update.vti",
        "fixed_grid_constrained_step_summary.json",
    ):
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, target_dir / name)
