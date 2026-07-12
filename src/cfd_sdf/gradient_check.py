from __future__ import annotations

import csv
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .grid import UniformGrid
from .sensitivity import (
    evaluate_mock_density_functionals,
    load_density_state,
    read_sensitivity_vti,
    write_mock_sensitivity_artifacts,
    write_vti_scalar_arrays,
)


GRADIENT_CHECK_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GradientCheckSample:
    sample_index: int
    i: int
    j: int
    k: int
    density: float
    method: str
    epsilon: float
    objective_base: float | None
    objective_plus: float | None
    objective_minus: float | None
    finite_difference: float | None
    analytic_sensitivity: float
    absolute_error: float | None
    relative_error: float | None
    sign_match: bool | None
    classification: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GradientCheckSummary:
    design_state_json: Path
    sensitivity_vti: Path
    output_dir: Path
    report_json: Path
    samples_csv: Path
    check_vti: Path
    sample_count: int
    ok_count: int
    sign_mismatch_count: int
    relative_error_count: int
    failed_perturbation_count: int
    max_relative_error: float | None
    mean_relative_error: float | None
    samples: list[GradientCheckSample]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("design_state_json", "sensitivity_vti", "output_dir", "report_json", "samples_csv", "check_vti"):
            data[key] = str(data[key])
        data["samples"] = [sample.to_dict() for sample in self.samples]
        return data


def run_finite_difference_gradient_check(
    design_state_json: Path,
    *,
    sensitivity_vti: Path | None = None,
    output_dir: Path | None = None,
    sample_count: int = 8,
    epsilon: float = 1.0e-3,
    method: str = "auto",
    tolerance: float = 1.0e-2,
    seed: int = 1,
) -> GradientCheckSummary:
    if sample_count < 1:
        raise ValueError("sample_count must be >= 1")
    if epsilon <= 0.0:
        raise ValueError("epsilon must be > 0")
    if method not in {"auto", "forward", "central"}:
        raise ValueError("method must be one of: auto, forward, central")
    if tolerance < 0.0:
        raise ValueError("tolerance must be >= 0")

    density_state = load_density_state(design_state_json)
    output_dir = output_dir or (density_state.design_state_json.parent / "gradient_check")
    output_dir.mkdir(parents=True, exist_ok=True)
    if sensitivity_vti is None:
        sensitivity_artifacts = write_mock_sensitivity_artifacts(density_state.design_state_json, output_dir=output_dir)
        sensitivity_vti = sensitivity_artifacts.sensitivity_vti

    sensitivity_grid, sensitivity_arrays = read_sensitivity_vti(sensitivity_vti)
    _assert_same_grid(density_state.grid, sensitivity_grid)
    active = (sensitivity_arrays["active_mask"] > 0) & density_state.allowed_mask
    analytic = sensitivity_arrays["objective_density_sensitivity"].astype(np.float64, copy=False)
    candidate_indices = np.argwhere(active & np.isfinite(analytic))
    if len(candidate_indices) == 0:
        raise ValueError("No active sensitivity cells are available for finite-difference checking.")

    rng = random.Random(seed)
    selected = candidate_indices.tolist()
    rng.shuffle(selected)
    selected = selected[: min(sample_count, len(selected))]
    base_objective = evaluate_mock_density_functionals(density_state)["objective"]
    samples = [
        _check_one_sample(
            density_state=density_state,
            analytic=analytic,
            index_tuple=tuple(int(value) for value in index_tuple),
            sample_index=sample_index,
            base_objective=base_objective,
            epsilon=epsilon,
            requested_method=method,
            tolerance=tolerance,
        )
        for sample_index, index_tuple in enumerate(selected)
    ]

    report_json = output_dir / "finite_difference_check.json"
    samples_csv = output_dir / "finite_difference_samples.csv"
    check_vti = output_dir / "finite_difference_check.vti"
    summary = _build_summary(
        design_state_json=density_state.design_state_json,
        sensitivity_vti=sensitivity_vti,
        output_dir=output_dir,
        report_json=report_json,
        samples_csv=samples_csv,
        check_vti=check_vti,
        samples=samples,
    )
    report_json.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    _write_samples_csv(samples_csv, samples)
    _write_check_vti(density_state.grid, analytic, samples, check_vti)
    return summary


def _check_one_sample(
    *,
    density_state,
    analytic: np.ndarray,
    index_tuple: tuple[int, int, int],
    sample_index: int,
    base_objective: float,
    epsilon: float,
    requested_method: str,
    tolerance: float,
) -> GradientCheckSample:
    i, j, k = index_tuple
    density_value = float(density_state.density[index_tuple])
    perturbation_method = _select_perturbation_method(density_value, epsilon, requested_method)
    analytic_value = float(analytic[index_tuple])
    if perturbation_method is None:
        return GradientCheckSample(
            sample_index=sample_index,
            i=i,
            j=j,
            k=k,
            density=density_value,
            method=requested_method,
            epsilon=epsilon,
            objective_base=base_objective,
            objective_plus=None,
            objective_minus=None,
            finite_difference=None,
            analytic_sensitivity=analytic_value,
            absolute_error=None,
            relative_error=None,
            sign_match=None,
            classification="failed_perturbation",
        )

    objective_plus = None
    objective_minus = None
    if perturbation_method in {"forward", "central"}:
        plus_density = density_state.density.copy()
        plus_density[index_tuple] = min(1.0, density_value + epsilon)
        objective_plus = evaluate_mock_density_functionals(density_state, plus_density)["objective"]
    if perturbation_method in {"backward", "central"}:
        minus_density = density_state.density.copy()
        minus_density[index_tuple] = max(0.0, density_value - epsilon)
        objective_minus = evaluate_mock_density_functionals(density_state, minus_density)["objective"]

    if perturbation_method == "central":
        finite_difference = (float(objective_plus) - float(objective_minus)) / (2.0 * epsilon)
    elif perturbation_method == "forward":
        finite_difference = (float(objective_plus) - base_objective) / epsilon
    else:
        finite_difference = (base_objective - float(objective_minus)) / epsilon

    absolute_error = abs(finite_difference - analytic_value)
    denominator = max(abs(finite_difference), abs(analytic_value), 1.0e-12)
    relative_error = absolute_error / denominator
    sign_match = _sign_match(finite_difference, analytic_value)
    if not sign_match:
        classification = "sign_mismatch"
    elif relative_error > tolerance:
        classification = "relative_error"
    else:
        classification = "ok"

    return GradientCheckSample(
        sample_index=sample_index,
        i=i,
        j=j,
        k=k,
        density=density_value,
        method=perturbation_method,
        epsilon=epsilon,
        objective_base=base_objective,
        objective_plus=float(objective_plus) if objective_plus is not None else None,
        objective_minus=float(objective_minus) if objective_minus is not None else None,
        finite_difference=float(finite_difference),
        analytic_sensitivity=analytic_value,
        absolute_error=float(absolute_error),
        relative_error=float(relative_error),
        sign_match=sign_match,
        classification=classification,
    )


def _select_perturbation_method(density_value: float, epsilon: float, requested_method: str) -> str | None:
    can_forward = density_value + epsilon <= 1.0
    can_backward = density_value - epsilon >= 0.0
    if requested_method == "central":
        return "central" if can_forward and can_backward else None
    if requested_method == "forward":
        return "forward" if can_forward else None
    if can_forward and can_backward:
        return "central"
    if can_forward:
        return "forward"
    if can_backward:
        return "backward"
    return None


def _sign_match(finite_difference: float, analytic_value: float) -> bool:
    sign_tolerance = 1.0e-12
    if abs(finite_difference) <= sign_tolerance or abs(analytic_value) <= sign_tolerance:
        return True
    return finite_difference * analytic_value > 0.0


def _build_summary(
    *,
    design_state_json: Path,
    sensitivity_vti: Path,
    output_dir: Path,
    report_json: Path,
    samples_csv: Path,
    check_vti: Path,
    samples: list[GradientCheckSample],
) -> GradientCheckSummary:
    relative_errors = [sample.relative_error for sample in samples if sample.relative_error is not None]
    return GradientCheckSummary(
        design_state_json=design_state_json,
        sensitivity_vti=sensitivity_vti,
        output_dir=output_dir,
        report_json=report_json,
        samples_csv=samples_csv,
        check_vti=check_vti,
        sample_count=len(samples),
        ok_count=sum(1 for sample in samples if sample.classification == "ok"),
        sign_mismatch_count=sum(1 for sample in samples if sample.classification == "sign_mismatch"),
        relative_error_count=sum(1 for sample in samples if sample.classification == "relative_error"),
        failed_perturbation_count=sum(1 for sample in samples if sample.classification == "failed_perturbation"),
        max_relative_error=float(max(relative_errors)) if relative_errors else None,
        mean_relative_error=float(np.mean(relative_errors)) if relative_errors else None,
        samples=samples,
    )


def _write_samples_csv(path: Path, samples: list[GradientCheckSample]) -> None:
    fieldnames = list(GradientCheckSample.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for sample in samples:
            writer.writerow(sample.to_dict())


def _write_check_vti(grid: UniformGrid, analytic: np.ndarray, samples: list[GradientCheckSample], path: Path) -> None:
    sampled_mask = np.zeros(grid.shape, dtype=np.uint8)
    finite_difference = np.full(grid.shape, np.nan, dtype=np.float32)
    relative_error = np.full(grid.shape, np.nan, dtype=np.float32)
    classification_code = np.zeros(grid.shape, dtype=np.int16)
    code_by_classification = {
        "ok": 1,
        "sign_mismatch": 2,
        "relative_error": 3,
        "failed_perturbation": 4,
    }
    for sample in samples:
        index_tuple = (sample.i, sample.j, sample.k)
        sampled_mask[index_tuple] = 1
        classification_code[index_tuple] = code_by_classification.get(sample.classification, 0)
        if sample.finite_difference is not None:
            finite_difference[index_tuple] = sample.finite_difference
        if sample.relative_error is not None:
            relative_error[index_tuple] = sample.relative_error

    write_vti_scalar_arrays(
        grid,
        {
            "sampled_mask": sampled_mask,
            "analytic_sensitivity": analytic.astype(np.float32, copy=False),
            "finite_difference_sensitivity": finite_difference,
            "relative_error": relative_error,
            "classification_code": classification_code,
        },
        path,
    )


def _assert_same_grid(left: UniformGrid, right: UniformGrid) -> None:
    if left.shape != right.shape:
        raise ValueError(f"Density grid shape {left.shape} does not match sensitivity grid shape {right.shape}")
    if not np.allclose(left.origin, right.origin):
        raise ValueError("Density grid origin does not match sensitivity grid origin")
    if not np.isclose(left.spacing, right.spacing):
        raise ValueError("Density grid spacing does not match sensitivity grid spacing")
