from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pyvista as pv


@dataclass(frozen=True)
class PorousForceGradientValidation:
    status: str
    baseline_objective: float
    plus_objective: float
    minus_objective: float
    epsilon: float
    finite_difference_derivative: float
    adjoint_directional_derivative: float
    absolute_error: float
    relative_error: float
    relative_error_tolerance: float
    sign_match: bool
    perturbed_cell_count: int
    baseline_solver_completed: bool
    plus_solver_completed: bool
    minus_solver_completed: bool
    baseline_primal_converged: bool
    plus_primal_converged: bool
    minus_primal_converged: bool
    objective_runtime_type_loaded: bool
    brinkman_sensitivity_observed: bool
    baseline_objective_file: Path
    plus_objective_file: Path
    minus_objective_file: Path
    alpha_vtk: Path
    sensitivity_vtk: Path
    report_json: Path
    report_markdown: Path

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        data["ok"] = self.ok
        return data


@dataclass(frozen=True)
class EfficiencyConstraintGradientValidation:
    status: str
    efficiency_min: float
    epsilon: float
    baseline_constraint: float
    plus_constraint: float
    minus_constraint: float
    finite_difference_derivative: float
    adjoint_directional_derivative: float
    absolute_error: float
    relative_error: float
    relative_error_tolerance: float
    sign_match: bool
    perturbed_cell_count: int
    separate_sensitivity_fields: bool
    sensitivity_vtk: Path
    report_json: Path
    report_markdown: Path

    @property
    def ok(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        data["ok"] = self.ok
        return data


def validate_porous_force_gradient(
    baseline_case_dir: Path,
    plus_case_dir: Path,
    minus_case_dir: Path,
    *,
    output_dir: Path,
    epsilon: float = 0.01,
    baseline_alpha: float = 0.5,
    objective_name: str = "drag",
    sensitivity_array: str = "topOSensas1",
    relative_error_tolerance: float = 0.1,
) -> PorousForceGradientValidation:
    if epsilon <= 0:
        raise ValueError("epsilon must be greater than zero")
    if relative_error_tolerance < 0:
        raise ValueError("relative_error_tolerance must be non-negative")

    baseline_case_dir = baseline_case_dir.resolve()
    plus_case_dir = plus_case_dir.resolve()
    minus_case_dir = minus_case_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_objective_file, baseline_objective = _read_objective(
        baseline_case_dir,
        objective_name,
    )
    plus_objective_file, plus_objective = _read_objective(
        plus_case_dir,
        objective_name,
    )
    minus_objective_file, minus_objective = _read_objective(
        minus_case_dir,
        objective_name,
    )

    alpha_vtk, alpha = _find_cell_array(baseline_case_dir, "alpha")
    sensitivity_vtk, sensitivity = _find_cell_array(
        baseline_case_dir,
        sensitivity_array,
    )
    if alpha.shape != sensitivity.shape:
        raise ValueError(
            f"alpha shape {alpha.shape} does not match sensitivity shape {sensitivity.shape}"
        )

    perturbation_mask = np.isclose(alpha, baseline_alpha, rtol=0.0, atol=1.0e-8)
    perturbed_cell_count = int(np.count_nonzero(perturbation_mask))
    if perturbed_cell_count == 0:
        raise ValueError(f"No alpha cells match baseline value {baseline_alpha}")

    finite_difference = (plus_objective - minus_objective) / (2.0 * epsilon)
    adjoint_derivative = float(np.sum(sensitivity[perturbation_mask], dtype=np.float64))
    absolute_error = abs(finite_difference - adjoint_derivative)
    relative_error = absolute_error / max(
        abs(finite_difference),
        abs(adjoint_derivative),
        1.0e-30,
    )
    sign_match = _sign_match(finite_difference, adjoint_derivative)

    baseline_log = _read_solver_log(baseline_case_dir)
    plus_log = _read_solver_log(plus_case_dir)
    minus_log = _read_solver_log(minus_case_dir)
    baseline_completed = _solver_completed(baseline_log)
    plus_completed = _solver_completed(plus_log)
    minus_completed = _solver_completed(minus_log)
    baseline_primal_converged = "op1 solution converged" in baseline_log
    plus_primal_converged = "op1 solution converged" in plus_log
    minus_primal_converged = "op1 solution converged" in minus_log
    runtime_type_loaded = "of type porousDirectionalForce" in baseline_log
    brinkman_sensitivity = "Postprocessing Brinkman sensitivities for field U" in baseline_log

    ok = all(
        (
            baseline_completed,
            plus_completed,
            minus_completed,
            baseline_primal_converged,
            plus_primal_converged,
            minus_primal_converged,
            runtime_type_loaded,
            brinkman_sensitivity,
            sign_match,
            relative_error <= relative_error_tolerance,
        )
    )
    report_json = output_dir / "porous_force_gradient_validation.json"
    report_markdown = output_dir / "porous_force_gradient_validation.md"
    result = PorousForceGradientValidation(
        status="pass" if ok else "fail",
        baseline_objective=baseline_objective,
        plus_objective=plus_objective,
        minus_objective=minus_objective,
        epsilon=epsilon,
        finite_difference_derivative=finite_difference,
        adjoint_directional_derivative=adjoint_derivative,
        absolute_error=absolute_error,
        relative_error=relative_error,
        relative_error_tolerance=relative_error_tolerance,
        sign_match=sign_match,
        perturbed_cell_count=perturbed_cell_count,
        baseline_solver_completed=baseline_completed,
        plus_solver_completed=plus_completed,
        minus_solver_completed=minus_completed,
        baseline_primal_converged=baseline_primal_converged,
        plus_primal_converged=plus_primal_converged,
        minus_primal_converged=minus_primal_converged,
        objective_runtime_type_loaded=runtime_type_loaded,
        brinkman_sensitivity_observed=brinkman_sensitivity,
        baseline_objective_file=baseline_objective_file,
        plus_objective_file=plus_objective_file,
        minus_objective_file=minus_objective_file,
        alpha_vtk=alpha_vtk,
        sensitivity_vtk=sensitivity_vtk,
        report_json=report_json.resolve(),
        report_markdown=report_markdown.resolve(),
    )
    report_json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    report_markdown.write_text(_markdown(result), encoding="utf-8")
    return result


def validate_efficiency_constraint_gradient(
    baseline_case_dir: Path,
    plus_case_dir: Path,
    minus_case_dir: Path,
    *,
    output_dir: Path,
    efficiency_min: float,
    epsilon: float = 0.005,
    baseline_alpha: float = 0.5,
    drag_objective_name: str = "drag",
    downforce_objective_name: str = "downforce2d",
    drag_sensitivity_array: str = "topOSensas1",
    downforce_sensitivity_array: str = "topOSensdownforce2d",
    relative_error_tolerance: float = 0.1,
) -> EfficiencyConstraintGradientValidation:
    if efficiency_min <= 0:
        raise ValueError("efficiency_min must be greater than zero")
    if epsilon <= 0:
        raise ValueError("epsilon must be greater than zero")
    if relative_error_tolerance < 0:
        raise ValueError("relative_error_tolerance must be non-negative")

    baseline_case_dir = baseline_case_dir.resolve()
    plus_case_dir = plus_case_dir.resolve()
    minus_case_dir = minus_case_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    _, baseline_drag = _read_objective(baseline_case_dir, drag_objective_name)
    _, plus_drag = _read_objective(plus_case_dir, drag_objective_name)
    _, minus_drag = _read_objective(minus_case_dir, drag_objective_name)
    _, baseline_downforce = _read_objective(baseline_case_dir, downforce_objective_name)
    _, plus_downforce = _read_objective(plus_case_dir, downforce_objective_name)
    _, minus_downforce = _read_objective(minus_case_dir, downforce_objective_name)

    alpha_vtk, alpha = _find_cell_array(baseline_case_dir, "alpha")
    drag_vtk, drag_sensitivity = _find_cell_array(
        baseline_case_dir,
        drag_sensitivity_array,
    )
    downforce_vtk, downforce_sensitivity = _find_cell_array(
        baseline_case_dir,
        downforce_sensitivity_array,
    )
    if not (alpha.shape == drag_sensitivity.shape == downforce_sensitivity.shape):
        raise ValueError("alpha, drag sensitivity, and downforce sensitivity shapes must match")
    if drag_vtk != downforce_vtk:
        raise ValueError("drag and downforce sensitivity arrays must share one VTK cell ordering")

    perturbation_mask = np.isclose(alpha, baseline_alpha, rtol=0.0, atol=1.0e-8)
    perturbed_cell_count = int(np.count_nonzero(perturbation_mask))
    if perturbed_cell_count == 0:
        raise ValueError(f"No alpha cells match baseline value {baseline_alpha}")

    baseline_constraint = efficiency_min * baseline_drag - baseline_downforce
    plus_constraint = efficiency_min * plus_drag - plus_downforce
    minus_constraint = efficiency_min * minus_drag - minus_downforce
    finite_difference = (plus_constraint - minus_constraint) / (2.0 * epsilon)
    constraint_sensitivity = (
        efficiency_min * drag_sensitivity - downforce_sensitivity
    )
    adjoint_derivative = float(
        np.sum(constraint_sensitivity[perturbation_mask], dtype=np.float64)
    )
    absolute_error = abs(finite_difference - adjoint_derivative)
    relative_error = absolute_error / max(
        abs(finite_difference),
        abs(adjoint_derivative),
        1.0e-30,
    )
    sign_match = _sign_match(finite_difference, adjoint_derivative)
    separate_fields = bool(
        np.linalg.norm(drag_sensitivity) > 0
        and np.linalg.norm(downforce_sensitivity) > 0
        and not np.allclose(drag_sensitivity, downforce_sensitivity)
    )
    logs = (
        _read_solver_log(baseline_case_dir),
        _read_solver_log(plus_case_dir),
        _read_solver_log(minus_case_dir),
    )
    solvers_ok = all(_solver_completed(log) for log in logs)
    primal_converged = all("op1 solution converged" in log for log in logs)
    ok = all(
        (
            solvers_ok,
            primal_converged,
            separate_fields,
            sign_match,
            relative_error <= relative_error_tolerance,
        )
    )

    output_vtk = output_dir / "fixed_grid_sensitivity.vtu"
    mesh = pv.read(drag_vtk)
    mesh.cell_data["d_drag_d_alpha"] = drag_sensitivity
    mesh.cell_data["d_downforce_d_alpha"] = downforce_sensitivity
    mesh.cell_data["d_efficiency_constraint_d_alpha"] = constraint_sensitivity
    mesh.cell_data["perturbation_mask"] = perturbation_mask.astype(np.uint8)
    mesh.save(output_vtk)

    report_json = output_dir / "efficiency_constraint_gradient_validation.json"
    report_markdown = output_dir / "efficiency_constraint_gradient_validation.md"
    result = EfficiencyConstraintGradientValidation(
        status="pass" if ok else "fail",
        efficiency_min=efficiency_min,
        epsilon=epsilon,
        baseline_constraint=baseline_constraint,
        plus_constraint=plus_constraint,
        minus_constraint=minus_constraint,
        finite_difference_derivative=finite_difference,
        adjoint_directional_derivative=adjoint_derivative,
        absolute_error=absolute_error,
        relative_error=relative_error,
        relative_error_tolerance=relative_error_tolerance,
        sign_match=sign_match,
        perturbed_cell_count=perturbed_cell_count,
        separate_sensitivity_fields=separate_fields,
        sensitivity_vtk=output_vtk.resolve(),
        report_json=report_json.resolve(),
        report_markdown=report_markdown.resolve(),
    )
    report_json.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    report_markdown.write_text(_efficiency_markdown(result), encoding="utf-8")
    return result


def _read_objective(case_dir: Path, objective_name: str) -> tuple[Path, float]:
    objective_root = case_dir / "optimisation" / "objective"
    candidates = sorted(
        path
        for path in objective_root.glob(f"**/{objective_name}*")
        if path.is_file() and "Instant" not in path.name
    )
    if not candidates:
        raise FileNotFoundError(
            f"No objective file starting with {objective_name!r} under {objective_root}"
        )
    path = candidates[-1]
    rows = [
        line.split()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not rows:
        raise ValueError(f"No objective data rows in {path}")
    row = rows[-1]
    value_index = 2 if len(row) >= 3 else 1
    return path.resolve(), float(row[value_index])


def _find_cell_array(case_dir: Path, array_name: str) -> tuple[Path, np.ndarray]:
    for path in sorted((case_dir / "VTK").glob("**/internal.vtu")):
        mesh = pv.read(path)
        if array_name in mesh.cell_data:
            values = np.asarray(mesh.cell_data[array_name], dtype=np.float64)
            return path.resolve(), values
    raise FileNotFoundError(f"Cell array {array_name!r} not found under {case_dir / 'VTK'}")


def _read_solver_log(case_dir: Path) -> str:
    path = case_dir / "log.adjointOptimisationFoam"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _solver_completed(log_text: str) -> bool:
    return (
        "\nEnd\n" in log_text
        and "Finalising parallel run" in log_text
        and "FOAM FATAL" not in log_text
    )


def _sign_match(left: float, right: float) -> bool:
    if math.isclose(left, 0.0, abs_tol=1.0e-12):
        return math.isclose(right, 0.0, abs_tol=1.0e-12)
    if math.isclose(right, 0.0, abs_tol=1.0e-12):
        return False
    return left * right > 0.0


def _markdown(result: PorousForceGradientValidation) -> str:
    all_primal_converged = all(
        (
            result.baseline_primal_converged,
            result.plus_primal_converged,
            result.minus_primal_converged,
        )
    )
    return (
        "# Porous Force Gradient Validation\n\n"
        f"- Status: `{result.status}`\n"
        f"- Baseline objective: `{result.baseline_objective:.12g}`\n"
        f"- Plus objective: `{result.plus_objective:.12g}`\n"
        f"- Minus objective: `{result.minus_objective:.12g}`\n"
        f"- Epsilon: `{result.epsilon:.12g}`\n"
        f"- Perturbed cells: `{result.perturbed_cell_count}`\n"
        f"- Finite-difference derivative: `{result.finite_difference_derivative:.12g}`\n"
        f"- Adjoint directional derivative: `{result.adjoint_directional_derivative:.12g}`\n"
        f"- Relative error: `{result.relative_error:.6%}`\n"
        f"- Relative-error tolerance: `{result.relative_error_tolerance:.6%}`\n"
        f"- Sign match: `{str(result.sign_match).lower()}`\n"
        f"- All primal solves converged: `{str(all_primal_converged).lower()}`\n"
        f"- Brinkman sensitivity observed: "
        f"`{str(result.brinkman_sensitivity_observed).lower()}`\n"
    )


def _efficiency_markdown(result: EfficiencyConstraintGradientValidation) -> str:
    return (
        "# Efficiency Constraint Gradient Validation\n\n"
        f"- Status: `{result.status}`\n"
        f"- Efficiency minimum: `{result.efficiency_min:.12g}`\n"
        f"- Epsilon: `{result.epsilon:.12g}`\n"
        f"- Baseline constraint: `{result.baseline_constraint:.12g}`\n"
        f"- Plus constraint: `{result.plus_constraint:.12g}`\n"
        f"- Minus constraint: `{result.minus_constraint:.12g}`\n"
        f"- Finite-difference derivative: `{result.finite_difference_derivative:.12g}`\n"
        f"- Adjoint directional derivative: `{result.adjoint_directional_derivative:.12g}`\n"
        f"- Relative error: `{result.relative_error:.6%}`\n"
        f"- Relative-error tolerance: `{result.relative_error_tolerance:.6%}`\n"
        f"- Sign match: `{str(result.sign_match).lower()}`\n"
        f"- Separate sensitivity fields: `{str(result.separate_sensitivity_fields).lower()}`\n"
        f"- Sensitivity VTK: `{result.sensitivity_vtk}`\n"
    )
