"""Numerically validate an immutable localized G2 FD run.

Preparation and execution are intentionally separate from this module.  This
is the only boundary that computes a finite-difference derivative or applies
the Sol-reviewed noise and acceptance protocol.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Mapping

import numpy as np

from .localized_alpha_reference_binding import load_and_verify_localized_alpha_reference_binding
from .localized_design_transfer import LocalizedDesignToCfdTransfer
from .localized_filter_projection import (
    apply_localized_cone_filter_adjoint,
    localized_heaviside_projection_derivative,
    read_canonical_filter_config,
    read_canonical_projection_config,
)
from .localized_g2_fd_preparation import LOCALIZED_G2_FD_PREPARATION_FILENAME
from .localized_g2_fd_runner import (
    LOCALIZED_G2_FD_RUN_FILENAME,
    LOCALIZED_G2_FD_RUN_KIND,
    LOCALIZED_G2_FD_RUN_SCHEMA_VERSION,
    _verify_prepared_experiment,
)
from .localized_openfoam_alpha_case import validate_localized_openfoam_alpha_case


LOCALIZED_G2_FD_VALIDATION_SCHEMA_VERSION = 1
LOCALIZED_G2_FD_VALIDATION_KIND = "localized_g2_openfoam_fd_validation"
LOCALIZED_G2_FD_VALIDATION_FILENAME = "localized_g2_openfoam_fd_validation.json"
LOCALIZED_G2_FD_VALIDATION_MARKDOWN_FILENAME = "localized_g2_openfoam_fd_validation.md"


@dataclass(frozen=True)
class LocalizedG2FdValidation:
    path: Path
    report_json: Path
    report_markdown: Path
    status: str
    mode: str
    selected_epsilon: float | None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key in ("path", "report_json", "report_markdown"):
            data[key] = str(data[key])
        return data


def validate_localized_g2_openfoam_fd_direction(
    prepared_experiment_path: str | Path,
    run_report_path: str | Path,
    *,
    output_dir: str | Path,
) -> LocalizedG2FdValidation:
    """Validate a completed run without mutating its inputs or criteria.

    Invalid or tampered provenance raises before creating ``output_dir``.
    A valid incomplete execution is published as ``execution_failed`` or
    ``inconclusive``; a valid numerical miss is published as ``fail``.
    """

    prepared_root, prepared = _verify_prepared_experiment(prepared_experiment_path)
    run_root, run = _verify_run_report(run_report_path, prepared_root, prepared)
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite localized G2 FD validation: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        if run["execution_status"] != "complete":
            payload = _base_report(prepared_root, prepared, run_root, run, status="execution_failed")
            payload["reason"] = "run_report_execution_status_is_not_complete"
        else:
            payload = _evaluate_completed_run(prepared_root, prepared, run_root, run)
        _write_json(staging / LOCALIZED_G2_FD_VALIDATION_FILENAME, payload)
        (staging / LOCALIZED_G2_FD_VALIDATION_MARKDOWN_FILENAME).write_text(
            _markdown(payload), encoding="utf-8", newline="\n"
        )
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return LocalizedG2FdValidation(
        path=destination, report_json=destination / LOCALIZED_G2_FD_VALIDATION_FILENAME,
        report_markdown=destination / LOCALIZED_G2_FD_VALIDATION_MARKDOWN_FILENAME,
        status=str(payload["status"]), mode=str(prepared["mode"]),
        selected_epsilon=payload.get("selected_epsilon") if isinstance(payload.get("selected_epsilon"), float) else None,
    )


def calculate_localized_g2_raw_directional_derivative(
    prepared_experiment_path: str | Path,
    dJ_dalpha: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Apply exactly ``F.T(P' * E.T*dJ_dalpha)`` and dot prepared direction."""

    root, prepared = _verify_prepared_experiment(prepared_experiment_path)
    return _chain_gradient(root, prepared, dJ_dalpha)


def _evaluate_completed_run(prepared_root: Path, prepared: Mapping[str, object], run_root: Path,
                            run: Mapping[str, object]) -> dict[str, object]:
    attempts = _verified_attempts(run_root, run, prepared)
    try:
        adjoint_attempt = attempts["adjoint"]
        response_id, gradient, gradient_provenance = _adjoint_gradient(adjoint_attempt, run_root)
        _require_execution_comparability(attempts, response_id)
        _response_value(adjoint_attempt, required_response_id=response_id)
        baseline = np.asarray([
            _response_value(attempts[f"reference_{index:03d}"], required_response_id=response_id)
            for index in range(1, int(run["baseline_repeats"]) + 1)
        ], dtype=np.float64)
        values = {label: _response_value(item, required_response_id=response_id) for label, item in attempts.items() if label != "adjoint"}
        raw_gradient, adjoint_directional = _chain_gradient(prepared_root, prepared, gradient, gradient_provenance)
    except _Inconclusive as exc:
        payload = _base_report(prepared_root, prepared, run_root, run, status="inconclusive")
        payload["reason"] = str(exc)
        return payload

    n0 = baseline.size
    mean0 = float(np.mean(baseline))
    sample_std = float(np.std(baseline, ddof=1))
    ladder = [float(value) for value in prepared["epsilon_ladder"]]
    mode = str(prepared["mode"])
    responses: dict[str, dict[str, float]] = {}
    deltas: dict[float, float] = {}
    scale_deviations: list[float] = []
    for h in ladder:
        plus = values[_label("plus", h)]
        if mode == "central":
            minus = values[_label("minus", h)]
            delta = (plus - minus) / 2.0
            derivative = (plus - minus) / (2.0 * h)
            scale_deviations.extend((abs(plus - mean0), abs(minus - mean0)))
            responses[_label("plus", h)] = {"value": plus}
            responses[_label("minus", h)] = {"value": minus}
        else:
            delta = plus - mean0
            derivative = delta / h
            scale_deviations.append(abs(delta))
            responses[_label("plus", h)] = {"value": plus}
        deltas[h] = delta
        responses[f"h={h:.17g}"] = {"delta": delta, "derivative": derivative}
    jscale = max(float(math.sqrt(float(np.mean(np.square(baseline))))), max(scale_deviations))
    sigma_j = max(sample_std, 1.0e-12 * jscale)
    if mode == "central":
        derivative_noise = {h: sigma_j / (math.sqrt(2.0) * h) for h in ladder}
        snr = {h: abs(deltas[h]) / (sigma_j / math.sqrt(2.0)) for h in ladder}
    else:
        derivative_noise = {h: sigma_j * math.sqrt(1.0 + 1.0 / n0) / h for h in ladder}
        snr = {h: abs(deltas[h]) / (sigma_j * math.sqrt(1.0 + 1.0 / n0)) for h in ladder}
    stability: dict[float, float] = {}
    candidates: list[float] = []
    for fine, coarse in ((ladder[1], ladder[0]), (ladder[2], ladder[1])):
        if mode == "central":
            sigma_delta = sigma_j / math.sqrt(2.0) * math.sqrt(1.0 / fine**2 + 1.0 / coarse**2)
        else:
            sigma_delta = sigma_j * math.sqrt(
                1.0 / fine**2 + 1.0 / coarse**2 + (1.0 / coarse - 1.0 / fine) ** 2 / n0
            )
        fine_d = responses[f"h={fine:.17g}"]["derivative"]
        coarse_d = responses[f"h={coarse:.17g}"]["derivative"]
        metric = abs(fine_d - coarse_d) / (0.05 * max(abs(fine_d), abs(coarse_d)) + 2.0 * sigma_delta)
        stability[fine] = metric
        if snr[fine] >= 10.0 and snr[coarse] >= 10.0 and metric <= 1.0:
            candidates.append(fine)
    if not candidates:
        payload = _base_report(prepared_root, prepared, run_root, run, status="inconclusive")
        payload.update({
            "reason": "fd_ladder_unqualified", "response_id": response_id,
            "baseline": _baseline_report(baseline, mean0, sample_std, jscale, sigma_j),
            "ladder": _ladder_report(ladder, responses, snr, derivative_noise, stability),
            "adjoint_directional_derivative": adjoint_directional,
        })
        return payload
    selected = min(candidates)
    fd = responses[f"h={selected:.17g}"]["derivative"]
    sigma_d = derivative_noise[selected]
    absolute_error = abs(fd - adjoint_directional)
    relative_error = absolute_error / max(abs(fd), abs(adjoint_directional), 1.0e-30)
    signs_match = _same_nonzero_sign(fd, adjoint_directional)
    gates = {
        "fd_signal": abs(fd) >= 5.0 * sigma_d,
        "adjoint_signal": abs(adjoint_directional) >= 5.0 * sigma_d,
        "same_nonzero_sign": signs_match,
        "relative_error": relative_error <= 0.10,
        "absolute_error": absolute_error <= 5.0 * sigma_d,
    }
    status = "pass" if all(gates.values()) else "fail"
    payload = _base_report(prepared_root, prepared, run_root, run, status=status)
    payload.update({
        "response_id": response_id, "selected_epsilon": selected,
        "baseline": _baseline_report(baseline, mean0, sample_std, jscale, sigma_j),
        "ladder": _ladder_report(ladder, responses, snr, derivative_noise, stability),
        "finite_difference_directional_derivative": fd,
        "adjoint_directional_derivative": adjoint_directional,
        "absolute_error": absolute_error, "relative_error": relative_error,
        "sigmaD": sigma_d, "gates": gates,
        "chain_gradient_sha256": _sha256_array(raw_gradient),
        "chain_gradient_formula": "g_raw=F.T(P_prime*(E.T*g_alpha))",
    })
    return payload


def _require_execution_comparability(attempts: Mapping[str, Mapping[str, object]], response_id: str) -> None:
    """Prove the conditional noise model applies before a numerical pass.

    Baseline noise can only be used for another fresh execution when their
    recorded runtime identity, declared final time, convergence, and named
    response are comparable.  Missing metadata is insufficient evidence, not
    a reason to silently relax the Sol-reviewed condition.
    """
    reference = attempts["reference_001"]
    reference_identity = _execution_identity(reference)
    reference_time = reference.get("final_time")
    if not isinstance(reference_time, (int, float, str)) or isinstance(reference_time, bool):
        raise _Inconclusive("reference baseline lacks a declared final_time")
    _require_converged(reference)
    _response_value(reference, required_response_id=response_id)
    for label, attempt in attempts.items():
        _require_converged(attempt)
        if attempt.get("final_time") != reference_time:
            raise _Inconclusive(f"attempt {label} final_time does not match the reference baseline")
        if _execution_identity(attempt) != reference_identity:
            raise _Inconclusive(f"attempt {label} execution_identity does not exactly match the reference baseline")
        _response_value(attempt, required_response_id=response_id)


def _require_converged(attempt: Mapping[str, object]) -> None:
    convergence = _mapping_or_inconclusive(attempt, "convergence", "run attempt lacks explicit convergence provenance")
    if convergence.get("status") != "converged":
        raise _Inconclusive("every compared execution must report convergence.status='converged'")


def _execution_identity(attempt: Mapping[str, object]) -> dict[str, object]:
    identity = _mapping_or_inconclusive(attempt, "execution_identity", "run attempt lacks execution_identity")
    required = ("runner", "backend", "container_image", "openfoam_version")
    # Preserve every declared field for exact identity comparison; the named
    # fields below are the irreducible minimum, while any runner-supplied mesh
    # or container detail is equally part of the evidence identity.
    result: dict[str, object] = dict(identity)
    for key in required:
        value = identity.get(key)
        if not isinstance(value, str) and value is not None:
            raise _Inconclusive(f"execution_identity.{key} must be a string or null")
        if key != "container_image" and (not isinstance(value, str) or not value):
            raise _Inconclusive(f"execution_identity.{key} is required for comparable noise evidence")
    # A runner that declares either side of a mesh/grid identity must declare
    # it identically everywhere; absence on all attempts remains explicitly
    # recorded as absent rather than guessed from a topology sensitivity.
    for key in ("mesh_sha256", "block_mesh_sha256", "grid_sha256", "cfd_grid_sha256"):
        if key in identity:
            value = identity[key]
            if not isinstance(value, str) or not value:
                raise _Inconclusive(f"execution_identity.{key} must be a non-empty string when supplied")
    return result


def _verify_run_report(path: str | Path, prepared_root: Path, prepared: Mapping[str, object]) -> tuple[Path, Mapping[str, object]]:
    report_path = Path(path).resolve()
    if report_path.name != LOCALIZED_G2_FD_RUN_FILENAME:
        raise ValueError("run report must use the canonical localized G2 FD run filename")
    run = _read_json(report_path)
    root = report_path.parent.resolve()
    if (run.get("schema_version") != LOCALIZED_G2_FD_RUN_SCHEMA_VERSION or run.get("kind") != LOCALIZED_G2_FD_RUN_KIND
            or run.get("status") not in {"run_complete", "execution_failed"}
            or run.get("execution_status") not in {"complete", "failed"} or run.get("validation_status") != "not_run"):
        raise ValueError("run report has an unsupported localized G2 FD execution contract")
    if (run.get("status") == "run_complete") != (run.get("execution_status") == "complete"):
        raise ValueError("run report status and execution_status are inconsistent")
    if run.get("mode") != prepared.get("mode") or run.get("epsilon_ladder") != prepared.get("epsilon_ladder"):
        raise ValueError("run report does not match the prepared mode or epsilon ladder")
    source = _mapping(run, "prepared_experiment")
    if Path(str(source.get("path", ""))).resolve() != prepared_root:
        raise ValueError("run report does not bind the exact prepared experiment path")
    if source.get("report_sha256") != _sha256_file(prepared_root / LOCALIZED_G2_FD_PREPARATION_FILENAME):
        raise ValueError("run report prepared experiment hash mismatch")
    if source.get("provenance") != prepared.get("provenance"):
        raise ValueError("run report prepared provenance mismatch")
    if not isinstance(run.get("baseline_repeats"), int) or int(run["baseline_repeats"]) < 2:
        raise ValueError("run report must record at least two baseline repeats")
    _verify_recorded_attempt_integrity(root, run, prepared)
    return root, run


def _verify_recorded_attempt_integrity(run_root: Path, run: Mapping[str, object], prepared: Mapping[str, object]) -> None:
    """Check every evidence-bearing attempt even when execution stopped early."""
    raw = run.get("attempts")
    if not isinstance(raw, list):
        raise ValueError("run report attempts must be a list")
    cases = _mapping(prepared, "cases")
    adjoint = _mapping(run, "adjoint")
    adjoint_name = adjoint.get("name")
    if not isinstance(adjoint_name, str) or not adjoint_name:
        raise ValueError("run report named adjoint is invalid")
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("run report attempt is invalid")
        phase, label = item.get("phase"), item.get("label")
        if phase == "adjoint":
            if label != adjoint_name:
                raise ValueError("run report adjoint label does not match its declared name")
            prepared_label = "reference"
        elif phase == "primal" and isinstance(label, str) and label.startswith("reference_"):
            prepared_label = "reference"
        elif phase == "primal":
            prepared_label = label
        else:
            raise ValueError("run report attempt phase is invalid")
        if not isinstance(prepared_label, str) or prepared_label not in cases:
            raise ValueError("run report attempt does not identify an immutable prepared case")
        case = (run_root / str(item.get("case_relative_path", ""))).resolve()
        _descendant(case, run_root, "run case escapes run evidence root")
        if _sha256_tree(case) != item.get("case_output_tree_sha256"):
            raise ValueError("run case output hash mismatch")
        artifact = validate_localized_openfoam_alpha_case(case)
        if artifact.alpha_values_sha256 != cases[prepared_label].get("alpha_values_sha256"):
            raise ValueError("run case alpha does not match its immutable prepared case")


def _verified_attempts(run_root: Path, run: Mapping[str, object], prepared: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = run.get("attempts")
    if not isinstance(raw, list):
        raise ValueError("run report attempts must be a list")
    expected = {f"reference_{index:03d}": "reference" for index in range(1, int(run["baseline_repeats"]) + 1)}
    adjoint = _mapping(run, "adjoint")
    name = adjoint.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("run report named adjoint is invalid")
    expected["adjoint"] = "reference"
    for h in prepared["epsilon_ladder"]:
        expected[_label("plus", float(h))] = _label("plus", float(h))
        if prepared["mode"] == "central":
            expected[_label("minus", float(h))] = _label("minus", float(h))
    required_sequence = [("primal", f"reference_{index:03d}") for index in range(1, int(run["baseline_repeats"]) + 1)]
    required_sequence.append(("adjoint", name))
    for sign in ("plus", "minus"):
        for h in prepared["epsilon_ladder"]:
            label = _label(sign, float(h))
            if label in expected:
                required_sequence.append(("primal", label))
    if [(item.get("phase"), item.get("label")) for item in raw if isinstance(item, Mapping)] != required_sequence:
        raise ValueError("run report attempt order is not the required fresh baseline, adjoint, and FD ladder sequence")
    found: dict[str, Mapping[str, object]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("run report attempt is invalid")
        phase, label = item.get("phase"), item.get("label")
        key = "adjoint" if phase == "adjoint" and label == name else str(label)
        if key not in expected or key in found:
            raise ValueError("run report attempts do not match the required fresh execution sequence")
        if item.get("status") != "success":
            raise ValueError("completed run report contains a failed required attempt")
        found[key] = item
    if set(found) != set(expected):
        raise ValueError("run report is missing required fresh baseline, adjoint, or FD attempts")
    adj = found["adjoint"]
    if adj.get("reference_primal_relative_path") != "primal/reference_001":
        raise ValueError("named adjoint is not bound to the exact first fresh reference baseline")
    return found


def _adjoint_gradient(attempt: Mapping[str, object], run_root: Path) -> tuple[str, np.ndarray, Mapping[str, object]]:
    response = _mapping(attempt, "response_provenance")
    response_id = response.get("response_id")
    if not isinstance(response_id, str) or not response_id:
        raise _Inconclusive("named adjoint lacks an explicitly recorded response_id")
    gradient = _mapping_or_inconclusive(response, "dJ_dalpha", "named adjoint lacks explicit dJ_dalpha provenance")
    if gradient.get("kind") != "dJ_dalpha" or gradient.get("response_id") != response_id:
        raise _Inconclusive("named adjoint dJ_dalpha provenance is not bound to its named response")
    case = (run_root / str(attempt["case_relative_path"])).resolve()
    relative = gradient.get("relative_path")
    if not isinstance(relative, str):
        raise _Inconclusive("named adjoint dJ_dalpha relative_path is missing")
    path = (case / relative).resolve(); _descendant(path, case, "dJ_dalpha path escapes adjoint case")
    if _sha256_file(path) != gradient.get("sha256"):
        raise ValueError("named adjoint dJ_dalpha file hash mismatch")
    values = np.load(path, allow_pickle=False)
    if not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.float64) or not values.dtype.isnative or values.ndim != 1 or not np.isfinite(values).all():
        raise _Inconclusive("named adjoint dJ_dalpha must be a finite native float64 vector")
    if gradient.get("dtype") != "float64" or gradient.get("shape") != [int(values.size)] or gradient.get("cell_order") != "x_fastest":
        raise _Inconclusive("named adjoint dJ_dalpha layout provenance is invalid")
    return response_id, values, gradient


def _response_value(attempt: Mapping[str, object], required_response_id: str | None = None) -> float:
    response = _mapping(attempt, "response_provenance")
    response_id = response.get("response_id")
    if not isinstance(response_id, str) or not response_id:
        raise _Inconclusive("run attempt lacks an explicitly recorded named response")
    if required_response_id is not None and response_id != required_response_id:
        raise _Inconclusive("run attempts do not bind the same named response as the adjoint")
    value = response.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise _Inconclusive("run attempt named response value is missing or non-finite")
    return float(value)


def _chain_gradient(prepared_root: Path, prepared: Mapping[str, object], gradient: np.ndarray,
                    gradient_provenance: Mapping[str, object] | None = None) -> tuple[np.ndarray, float]:
    provenance = _mapping(prepared, "provenance")
    binding = load_and_verify_localized_alpha_reference_binding(Path(str(provenance["alpha_reference_binding_path"])))
    state = binding.reference_state.manifest
    if gradient.shape != (binding.binding.cfd_grid.cell_count,):
        raise _Inconclusive("dJ_dalpha length does not match the verified CFD grid")
    if gradient_provenance is not None and gradient_provenance.get("cfd_grid_sha256") != binding.binding.cfd_grid_sha256:
        raise _Inconclusive("dJ_dalpha provenance does not bind the verified CFD grid")
    active_artifact = state.masks.get("active_design_mask")
    if active_artifact is None:
        raise ValueError("reference state lacks active_design_mask")
    active = np.load(state.path.parent / active_artifact.relative_path, mmap_mode="r", allow_pickle=False)
    filtered = np.load(state.path.parent / state.states["rho_filtered"].relative_path, mmap_mode="r", allow_pickle=False)
    filter_config = read_canonical_filter_config(state.path.parent / state.filter_config.relative_path)  # type: ignore[union-attr]
    projection_config = read_canonical_projection_config(state.path.parent / state.projection_config.relative_path)  # type: ignore[union-attr]
    transfer = LocalizedDesignToCfdTransfer.build(cfd_grid=binding.binding.cfd_grid, design_grid=state.grid)
    try:
        design_gradient = transfer.apply_adjoint(gradient)
        projection_derivative = localized_heaviside_projection_derivative(filtered, active, config=projection_config)
        design_gradient *= projection_derivative
        raw_gradient = apply_localized_cone_filter_adjoint(design_gradient, active, state.grid, config=filter_config)
        direction = np.load(prepared_root / "direction.npy", mmap_mode="r", allow_pickle=False)
        if direction.dtype != np.dtype(np.float64) or direction.shape != raw_gradient.shape:
            raise ValueError("prepared direction layout does not match local chain gradient")
        return raw_gradient, float(np.dot(raw_gradient, direction))
    finally:
        del active, filtered


def _base_report(prepared_root: Path, prepared: Mapping[str, object], run_root: Path, run: Mapping[str, object], *, status: str) -> dict[str, object]:
    return {
        "schema_version": LOCALIZED_G2_FD_VALIDATION_SCHEMA_VERSION,
        "kind": LOCALIZED_G2_FD_VALIDATION_KIND,
        "status": status,
        "mode": prepared["mode"], "epsilon_ladder": prepared["epsilon_ladder"],
        "prepared_experiment_path": str(prepared_root),
        "prepared_experiment_sha256": _sha256_file(prepared_root / LOCALIZED_G2_FD_PREPARATION_FILENAME),
        "run_report_path": str(run_root / LOCALIZED_G2_FD_RUN_FILENAME),
        "run_report_sha256": _sha256_file(run_root / LOCALIZED_G2_FD_RUN_FILENAME),
        "run_execution_status": run["execution_status"],
        "validation_protocol": _mapping(prepared, "validation_protocol"),
    }


def _baseline_report(values: np.ndarray, mean: float, std: float, scale: float, sigma: float) -> dict[str, object]:
    return {"values": values.tolist(), "n0": int(values.size), "Jbar0": mean, "sJ": std, "Jscale": scale, "sigmaJ": sigma}


def _ladder_report(ladder: list[float], responses: Mapping[str, Mapping[str, float]], snr: Mapping[float, float], noise: Mapping[float, float], stability: Mapping[float, float]) -> dict[str, object]:
    return {f"h={h:.17g}": {**responses[f"h={h:.17g}"], "SNR": snr[h], "sigmaD": noise[h], "Mstab": stability.get(h)} for h in ladder}


def _same_nonzero_sign(left: float, right: float) -> bool:
    return left != 0.0 and right != 0.0 and left * right > 0.0


def _label(sign: str, epsilon: float) -> str:
    return f"{sign}_h{epsilon:.17g}".replace("+", "p").replace("-", "m")


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read JSON: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError(f"{key} must be an object")
    return result


def _mapping_or_inconclusive(value: Mapping[str, object], key: str, message: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise _Inconclusive(message)
    return result


def _descendant(path: Path, parent: Path, message: str) -> None:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError as exc:
        raise ValueError(message) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_array(values: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest()


def _sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
        rel = item.relative_to(path).as_posix().encode("utf-8")
        if item.is_symlink():
            raise ValueError(f"symlink is forbidden in run evidence: {item}")
        if item.is_dir(): digest.update(b"D\0" + rel + b"\0")
        elif item.is_file():
            digest.update(b"F\0" + rel + b"\0")
            with item.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        else: raise ValueError(f"unsupported run evidence entry: {item}")
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _markdown(payload: Mapping[str, object]) -> str:
    lines = ["# Localized G2 OpenFOAM FD Validation", "", f"- Status: `{payload['status']}`", f"- Mode: `{payload['mode']}`"]
    if "reason" in payload: lines.append(f"- Reason: `{payload['reason']}`")
    if "selected_epsilon" in payload: lines.append(f"- Selected epsilon: `{payload['selected_epsilon']}`")
    if "relative_error" in payload: lines.append(f"- Relative error: `{payload['relative_error']}`")
    return "\n".join(lines) + "\n"


class _Inconclusive(Exception):
    pass


__all__ = [
    "LOCALIZED_G2_FD_VALIDATION_FILENAME", "LOCALIZED_G2_FD_VALIDATION_KIND",
    "LOCALIZED_G2_FD_VALIDATION_MARKDOWN_FILENAME", "LocalizedG2FdValidation",
    "calculate_localized_g2_raw_directional_derivative", "validate_localized_g2_openfoam_fd_direction",
]
