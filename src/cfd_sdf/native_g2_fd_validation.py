"""Fail-closed native OpenFOAM finite-difference direction checks for G2.

This is deliberately a *forward* state transfer only.  A canonical density
direction is averaged onto the uniform ``blockMesh`` cells with ``P @ d_rho``;
the baseline OpenFOAM ``alpha`` state is reconstructed from the executed
baseline case, never inferred by trying to invert ``P``.  The matching
canonical adjoint gradient is the Euclidean dual ``P.T @ g`` produced by
``openfoam_canonical_field_transfer``.

The staged cases are independent copies of a compiled bundle case and are
therefore suitable for Docker, WSL, local execution, or an externally injected
runner.  They never modify the evidence-bearing bundle or baseline run.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
from math import isfinite, sqrt
from pathlib import Path
import re
import shutil
import stat
from typing import Any

import numpy as np

from .canonical_grid_snapshot import load_and_verify_canonical_grid_snapshot
from .execution import OpenFoamRunResult, run_openfoam_case
from .openfoam_blockmesh_grid import read_openfoam_blockmesh_uniform_cartesian_grid
from .openfoam_canonical_field_transfer import _array_sha256
from .openfoam_field_reconstruction import reconstruct_final_decomposed_openfoam_fields
from .openfoam_grid_transfer import ExactCartesianOverlapTransfer
from .problem_spec import ProblemSpec, load_problem_spec, problem_spec_sha256


_KIND = "native_g2_openfoam_fd_direction"
_SCHEMA_VERSION = 1
_INTERNAL_FIELD = re.compile(
    r"\binternalField\s+(?:uniform\s+[^;]+|nonuniform\s+List<scalar>\s+\d+\s*\(\s*.*?\s*\))\s*;",
    flags=re.DOTALL,
)


@dataclass(frozen=True)
class NativeG2FDDirectionArtifacts:
    """Immutable paths for one prepared native FD direction experiment."""

    output_dir: Path
    plus_case_dir: Path
    minus_case_dir: Path
    direction_npz: Path
    provenance_json: Path
    flow_case_id: str
    response_id: str
    objective_id: str
    epsilon: float

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        return data


@dataclass(frozen=True)
class NativeG2FDDirectionValidation:
    """Comparison of staged native force values with a transferred adjoint."""

    status: str
    objective_id: str
    flow_case_id: str
    response_id: str
    units: str
    epsilon: float
    plus_raw_coefficient: float
    minus_raw_coefficient: float
    plus_objective_value: float
    minus_objective_value: float
    finite_difference_derivative: float
    adjoint_directional_derivative: float
    absolute_error: float
    relative_error: float
    relative_error_tolerance: float
    sign_match: bool
    response_conversion: Mapping[str, object]
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


def prepare_native_g2_openfoam_fd_direction(
    *,
    project_yaml: str | Path,
    bundle_dir: str | Path,
    baseline_case_dir: str | Path,
    canonical_snapshot_json: str | Path,
    canonical_gradient_dir: str | Path,
    flow_case_id: str,
    response_id: str,
    objective_id: str,
    canonical_density_direction: Sequence[float] | np.ndarray,
    epsilon: float,
    output_dir: str | Path,
    final_time: str | None = None,
) -> NativeG2FDDirectionArtifacts:
    """Stage a central FD experiment without creating a canonical state field.

    ``baseline_case_dir`` must be a completed decomposed run for the selected
    flow response.  Its final raw ``alpha`` is reconstructed in global cell
    order and is perturbed directly.  The compiled ``bundle_dir`` supplies the
    clean, reproducible case template.  A pre-existing ``output_dir`` is
    always rejected, which prevents accidental replacement of qualification or
    other evidence artifacts.
    """

    if not isinstance(epsilon, (int, float)) or isinstance(epsilon, bool) or not isfinite(float(epsilon)) or epsilon <= 0:
        raise ValueError("epsilon must be a positive finite number")
    spec = load_problem_spec(project_yaml)
    response = _response(spec, flow_case_id, response_id)
    objective_coefficient = _objective_term_coefficient(spec, objective_id, flow_case_id, response_id)
    bundle_root = Path(bundle_dir).resolve()
    baseline_root = Path(baseline_case_dir).resolve()
    output = Path(output_dir).resolve()
    if output.exists():
        raise ValueError(f"output_dir already exists: {output}")
    bundle = _verify_bundle(bundle_root, spec)
    template_case = _bundle_case_dir(bundle_root, bundle, flow_case_id)
    snapshot = load_and_verify_canonical_grid_snapshot(canonical_snapshot_json, spec)
    source_mesh = read_openfoam_blockmesh_uniform_cartesian_grid(template_case / "system" / "blockMeshDict")
    reconstructed = reconstruct_final_decomposed_openfoam_fields(
        baseline_root,
        adjoint_solver_id=f"resp_{response_id}",
        final_time=final_time,
    )
    if reconstructed.raw_alpha is None:
        raise ValueError("baseline reconstructed raw_alpha is required; state transfer is not supported")
    if source_mesh.grid.cell_count != reconstructed.raw_alpha.size:
        raise ValueError("baseline raw_alpha cell count does not match compiled blockMesh grid")
    transfer = ExactCartesianOverlapTransfer.build(
        source_grid=source_mesh.grid,
        target_grid=snapshot.snapshot.grid,
        source_active_mask=np.ones(source_mesh.grid.cell_count, dtype=bool),
        target_active_mask=np.ones(snapshot.snapshot.grid.cell_count, dtype=bool),
        expected_source_grid_sha256=source_mesh.grid_sha256,
        expected_target_grid_sha256=snapshot.snapshot.grid_sha256,
    )
    gradient, gradient_provenance = _load_and_verify_gradient(
        canonical_gradient_dir,
        snapshot_grid_sha256=snapshot.snapshot.grid_sha256,
        source_grid_sha256=source_mesh.grid_sha256,
        reconstructed=reconstructed,
    )
    direction = _canonical_direction(canonical_density_direction, snapshot.masks["active_design_mask"])
    source_direction = transfer.transfer_state_to_source(direction)
    baseline_alpha = np.asarray(reconstructed.raw_alpha, dtype=np.float64)
    plus_alpha = baseline_alpha + float(epsilon) * source_direction
    minus_alpha = baseline_alpha - float(epsilon) * source_direction
    _require_unit_interval(plus_alpha, "plus alpha")
    _require_unit_interval(minus_alpha, "minus alpha")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".{output.name}.staging"
    if staging.exists():
        raise FileExistsError(f"Refusing to use pre-existing staging directory: {staging}")
    try:
        staging.mkdir()
        plus_case = staging / "plus"
        minus_case = staging / "minus"
        shutil.copytree(template_case, plus_case)
        shutil.copytree(template_case, minus_case)
        _write_alpha_field(plus_case / "0.orig" / "alpha", plus_alpha)
        _write_alpha_field(minus_case / "0.orig" / "alpha", minus_alpha)
        _patch_allrun_to_restore_fd_alpha(plus_case / "Allrun")
        _patch_allrun_to_restore_fd_alpha(minus_case / "Allrun")
        direction_npz = staging / "direction.npz"
        np.savez_compressed(
            direction_npz,
            canonical_density_direction=direction,
            source_alpha_direction=source_direction,
            baseline_source_alpha=baseline_alpha,
            plus_source_alpha=plus_alpha,
            minus_source_alpha=minus_alpha,
            canonical_response_gradient=gradient,
        )
        conversion = _force_conversion(spec, response)
        provenance = {
            "schema_version": _SCHEMA_VERSION,
            "kind": _KIND,
            "status": "prepared",
            "problem_id": spec.problem_id,
            "problem_spec_sha256": problem_spec_sha256(spec),
            "bundle": {
                "path": str(bundle_root),
                "openfoam_case_bundle_sha256": _sha256_file(bundle_root / "openfoam_case_bundle.json"),
                "template_case": str(template_case),
                "template_case_compilation_sha256": _sha256_file(template_case / "openfoam_case_compilation.json"),
            },
            "baseline": {
                "case_dir": str(baseline_root),
                "raw_alpha_sha256": _array_sha256(baseline_alpha),
                "top_o_sensitivity_sha256": _array_sha256(reconstructed.top_o_sensitivity),
                "field_reconstruction": reconstructed.provenance,
            },
            "canonical": {
                "snapshot_path": str(snapshot.snapshot.path.resolve()),
                "snapshot_grid_sha256": snapshot.snapshot.grid_sha256,
                "active_design_mask_sha256": snapshot.snapshot.masks["active_design_mask"].sha256,
                "direction_sha256": _array_sha256(direction),
                "gradient_directory": str(Path(canonical_gradient_dir).resolve()),
                "gradient_provenance_sha256": _sha256_file(Path(canonical_gradient_dir) / "provenance.json"),
                "gradient_sha256": _array_sha256(gradient),
            },
            "transfer": {
                "state_map": "source_alpha_direction = P @ canonical_density_direction",
                "gradient_map": "canonical_gradient = P.T @ source_gradient",
                "source_grid_sha256": source_mesh.grid_sha256,
                "target_grid_sha256": snapshot.snapshot.grid_sha256,
                "coverage": "full source and target grid domains",
            },
            "fd": {
                "epsilon": float(epsilon),
                "alpha_bounds": [0.0, 1.0],
                "no_clipping": True,
                "source_state": "reconstructed_baseline_raw_alpha",
            },
            "response": {
                "flow_case_id": flow_case_id,
                "response_id": response_id,
                "objective_id": objective_id,
                "objective_term_coefficient": objective_coefficient,
                "units": "N",
                "conversion": conversion,
                "gradient_quantity": "porous_directional_force_coefficient_derivative",
            },
            "staged_files": {
                "direction_npz_sha256": _sha256_file(direction_npz),
                "plus_alpha_sha256": _sha256_file(plus_case / "0.orig" / "alpha"),
                "minus_alpha_sha256": _sha256_file(minus_case / "0.orig" / "alpha"),
                "plus_allrun_sha256": _sha256_file(plus_case / "Allrun"),
                "minus_allrun_sha256": _sha256_file(minus_case / "Allrun"),
            },
            "gradient_source": gradient_provenance,
        }
        provenance_path = staging / "provenance.json"
        _write_json(provenance_path, provenance)
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return NativeG2FDDirectionArtifacts(
        output_dir=output,
        plus_case_dir=output / "plus",
        minus_case_dir=output / "minus",
        direction_npz=output / "direction.npz",
        provenance_json=output / "provenance.json",
        flow_case_id=flow_case_id,
        response_id=response_id,
        objective_id=objective_id,
        epsilon=float(epsilon),
    )


def execute_native_g2_openfoam_fd_direction(
    artifacts: NativeG2FDDirectionArtifacts,
    *,
    backend: str = "auto",
    timeout_seconds: int | None = None,
    docker_image: str | None = None,
    runner: Callable[[Path], object] | None = None,
) -> tuple[object, object]:
    """Execute staged cases or invoke an injected runner for tests/integration."""

    if not artifacts.provenance_json.is_file():
        raise FileNotFoundError(f"Prepared FD provenance does not exist: {artifacts.provenance_json}")
    invoke = runner or (
        lambda case: run_openfoam_case(
            case,
            backend=backend,
            dry_run=False,
            timeout_seconds=timeout_seconds,
            docker_image=docker_image,
        )
    )
    plus_result = invoke(artifacts.plus_case_dir)
    minus_result = invoke(artifacts.minus_case_dir)
    for name, result in (("plus", plus_result), ("minus", minus_result)):
        if isinstance(result, OpenFoamRunResult) and not result.ok:
            raise RuntimeError(f"{name} OpenFOAM FD case failed: {result.summary_path}")
    return plus_result, minus_result


def validate_native_g2_openfoam_fd_direction(
    prepared_dir: str | Path,
    *,
    relative_error_tolerance: float = 0.25,
) -> NativeG2FDDirectionValidation:
    """Parse staged force coefficients and compare the central FD derivative.

    Only the declared ``force`` response is accepted.  OpenFOAM objective files
    are dimensionless porous-force coefficients, so values and the canonical
    gradient are converted to N using the ProblemSpec dynamic-pressure area
    factor before multiplying the selected objective term coefficient.
    """

    if not isinstance(relative_error_tolerance, (int, float)) or isinstance(relative_error_tolerance, bool) or relative_error_tolerance < 0:
        raise ValueError("relative_error_tolerance must be non-negative")
    root = Path(prepared_dir).resolve()
    provenance = _read_json(root / "provenance.json")
    _require(provenance.get("kind") == _KIND, "prepared provenance kind is invalid")
    _require(provenance.get("status") == "prepared", "prepared provenance status is invalid")
    response_data = _mapping(provenance, "response")
    canonical = _mapping(provenance, "canonical")
    fd = _mapping(provenance, "fd")
    response_id = _text(response_data, "response_id")
    flow_case_id = _text(response_data, "flow_case_id")
    objective_id = _text(response_data, "objective_id")
    epsilon = _positive_float(fd.get("epsilon"), "prepared epsilon")
    objective_coefficient = _finite_float(response_data.get("objective_term_coefficient"), "objective term coefficient")
    conversion = _mapping(response_data, "conversion")
    factor = _positive_float(conversion.get("factor_N_per_coefficient"), "force conversion factor")
    with np.load(root / "direction.npz", allow_pickle=False) as payload:
        direction = _finite_vector(payload["canonical_density_direction"], "canonical density direction")
        gradient = _finite_vector(payload["canonical_response_gradient"], "canonical response gradient")
    expected_direction_hash = _text(canonical, "direction_sha256")
    if _array_sha256(direction) != expected_direction_hash:
        raise ValueError("prepared canonical density direction hash mismatch")
    if _array_sha256(gradient) != _text(canonical, "gradient_sha256"):
        raise ValueError("prepared canonical response gradient hash mismatch")
    plus_raw = _read_final_response_coefficient(root / "plus", response_id)
    minus_raw = _read_final_response_coefficient(root / "minus", response_id)
    plus_value = objective_coefficient * factor * plus_raw
    minus_value = objective_coefficient * factor * minus_raw
    finite_difference = (plus_value - minus_value) / (2.0 * epsilon)
    adjoint = objective_coefficient * factor * float(np.dot(gradient, direction))
    absolute_error = abs(finite_difference - adjoint)
    relative_error = absolute_error / max(abs(finite_difference), abs(adjoint), 1.0e-30)
    sign_match = _sign_match(finite_difference, adjoint)
    status = "pass" if sign_match and relative_error <= float(relative_error_tolerance) else "fail"
    report_json = root / "native_g2_fd_direction_validation.json"
    report_markdown = root / "native_g2_fd_direction_validation.md"
    result = NativeG2FDDirectionValidation(
        status=status,
        objective_id=objective_id,
        flow_case_id=flow_case_id,
        response_id=response_id,
        units="N",
        epsilon=epsilon,
        plus_raw_coefficient=plus_raw,
        minus_raw_coefficient=minus_raw,
        plus_objective_value=plus_value,
        minus_objective_value=minus_value,
        finite_difference_derivative=finite_difference,
        adjoint_directional_derivative=adjoint,
        absolute_error=absolute_error,
        relative_error=relative_error,
        relative_error_tolerance=float(relative_error_tolerance),
        sign_match=sign_match,
        response_conversion=dict(conversion),
        report_json=report_json,
        report_markdown=report_markdown,
    )
    _write_json(report_json, result.to_dict())
    report_markdown.write_text(
        "# Native G2 OpenFOAM FD Direction Validation\n\n"
        f"- Status: `{result.status}`\n"
        f"- Response: `{result.flow_case_id}/{result.response_id}`\n"
        f"- Objective: `{result.objective_id}`\n"
        f"- Units: `{result.units}`\n"
        f"- Epsilon: `{result.epsilon:.12g}`\n"
        f"- Finite-difference derivative: `{result.finite_difference_derivative:.12g}`\n"
        f"- Transferred-adjoint directional derivative: `{result.adjoint_directional_derivative:.12g}`\n"
        f"- Relative error: `{result.relative_error:.6%}`\n",
        encoding="utf-8",
    )
    return result


def _load_and_verify_gradient(
    directory: str | Path,
    *,
    snapshot_grid_sha256: str,
    source_grid_sha256: str,
    reconstructed: Any,
) -> tuple[np.ndarray, Mapping[str, object]]:
    root = Path(directory).resolve()
    provenance = _read_json(root / "provenance.json")
    _require(provenance.get("kind") == "openfoam_canonical_gradient_transfer", "canonical gradient provenance kind is invalid")
    target = _mapping(provenance, "target")
    transfer = _mapping(provenance, "transfer")
    source = _mapping(provenance, "source")
    _require(target.get("grid_sha256") == snapshot_grid_sha256, "canonical gradient does not bind the requested snapshot grid")
    _require(transfer.get("source_grid_sha256") == source_grid_sha256, "canonical gradient does not bind the compiled blockMesh grid")
    _require(transfer.get("gradient_map") == "target_gradient = P.T @ source_gradient", "canonical gradient convention is unsupported")
    source_hashes = _mapping(source, "field_value_sha256")
    top_hash = _mapping(source_hashes, "top_o_sensitivity")
    raw_hash = _mapping(source_hashes, "raw_alpha")
    _require(top_hash.get("value_sha256") == _array_sha256(reconstructed.top_o_sensitivity), "canonical gradient baseline topOSens does not match the selected run")
    _require(reconstructed.raw_alpha is not None and raw_hash.get("value_sha256") == _array_sha256(reconstructed.raw_alpha), "canonical gradient baseline raw_alpha does not match the selected run")
    npz_path = root / "canonical_gradient.npz"
    with np.load(npz_path, allow_pickle=False) as payload:
        if set(payload.files) != {"top_o_sensitivity_gradient", "canonical_cell_indices"}:
            raise ValueError("canonical gradient NPZ has an unexpected array set")
        gradient = _finite_vector(payload["top_o_sensitivity_gradient"], "canonical response gradient")
        indices = payload["canonical_cell_indices"]
    if not np.array_equal(indices, np.arange(gradient.size, dtype=np.int64)):
        raise ValueError("canonical gradient cell indices are not canonical ascending integers")
    if gradient.size != int(target.get("cell_count", -1)):
        raise ValueError("canonical gradient cell count does not match provenance")
    exported = _mapping(provenance, "exported_arrays")
    exported_gradient = _mapping(exported, "top_o_sensitivity_gradient")
    _require(exported_gradient.get("sha256") == _array_sha256(gradient), "canonical gradient array hash mismatch")
    return gradient, provenance


def _canonical_direction(values: Sequence[float] | np.ndarray, active_mask: np.ndarray) -> np.ndarray:
    direction = _finite_vector(values, "canonical_density_direction")
    active = np.asarray(active_mask, dtype=np.uint8)
    if active.shape != direction.shape:
        raise ValueError("canonical_density_direction shape does not match active design mask")
    if np.any(np.abs(direction[active == 0]) > 1.0e-14):
        raise ValueError("canonical_density_direction must be zero outside active design cells")
    if not np.any(np.abs(direction[active != 0]) > 1.0e-14):
        raise ValueError("canonical_density_direction is zero on active design cells")
    return direction


def _verify_bundle(root: Path, spec: ProblemSpec) -> Mapping[str, object]:
    bundle = _read_json(root / "openfoam_case_bundle.json")
    _require(bundle.get("kind") == "openfoam_case_bundle", "bundle is not an OpenFOAM case bundle")
    _require(bundle.get("status") == "compiled" and bundle.get("compile_ready") is True, "bundle is not compiled and ready")
    _require(bundle.get("problem_id") == spec.problem_id, "bundle problem_id does not match project")
    _require(bundle.get("problem_spec_sha256") == problem_spec_sha256(spec), "bundle problem specification hash does not match project")
    return bundle


def _bundle_case_dir(root: Path, bundle: Mapping[str, object], flow_case_id: str) -> Path:
    flows = _mapping(bundle, "flow_cases")
    item = _mapping(flows, flow_case_id)
    relative = _text(item, "case_dir")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("bundle flow case directory escapes bundle root") from exc
    if not candidate.is_dir() or not (candidate / "system" / "blockMeshDict").is_file():
        raise FileNotFoundError(f"compiled bundle flow case is incomplete: {candidate}")
    if not (candidate / "openfoam_case_compilation.json").is_file():
        raise FileNotFoundError(f"compiled bundle case has no compilation metadata: {candidate}")
    return candidate


def _response(spec: ProblemSpec, flow_case_id: str, response_id: str):
    matches = [item for item in spec.responses if item.flow_case_id == flow_case_id and item.id == response_id]
    if len(matches) != 1:
        raise ValueError("flow_case_id/response_id must identify exactly one declared response")
    if matches[0].kind != "force":
        raise ValueError("native G2 FD direction validation only supports declared force responses")
    return matches[0]


def _objective_term_coefficient(spec: ProblemSpec, objective_id: str, flow_case_id: str, response_id: str) -> float:
    objectives = [item for item in spec.objectives if item.id == objective_id]
    if len(objectives) != 1:
        raise ValueError("objective_id must identify exactly one declared objective")
    if objectives[0].sense != "minimize":
        raise ValueError("native G2 FD objective must have minimize sense")
    matches = [item.coefficient for item in objectives[0].terms if item.flow_case_id == flow_case_id and item.response_id == response_id]
    if len(matches) != 1:
        raise ValueError("objective must contain exactly one selected flow_case_id/response_id term")
    return _finite_float(matches[0], "objective term coefficient")


def _force_conversion(spec: ProblemSpec, response: Any) -> dict[str, object]:
    if spec.reference_values is None or spec.reference_values.area_m2 is None:
        raise ValueError("force conversion requires reference_values.area_m2")
    flow = next(item for item in spec.flow_cases if item.id == response.flow_case_id)
    speed = sqrt(sum(float(value) ** 2 for value in flow.freestream_velocity_mps))
    factor = 0.5 * float(flow.fluid.density_kg_m3) * float(spec.reference_values.area_m2) * speed**2
    if not isfinite(factor) or factor <= 0.0:
        raise ValueError("declared force conversion factor is invalid")
    return {
        "source_quantity": "porous_directional_force_coefficient",
        "conversion_kind": "dynamic_pressure_area",
        "factor_N_per_coefficient": factor,
        "density_kg_m3": float(flow.fluid.density_kg_m3),
        "reference_area_m2": float(spec.reference_values.area_m2),
        "freestream_speed_mps": speed,
        "freestream_velocity_mps": list(flow.freestream_velocity_mps),
    }


def _write_alpha_field(path: Path, values: np.ndarray) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"compiled case alpha template is missing: {path}")
    # ``Path.write_text`` uses the host newline convention.  This staging
    # happens on Windows as well as Linux, while the resulting script is run
    # by Docker/WSL bash; normalize first and write bytes so it stays POSIX LF.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    replacement = "internalField nonuniform List<scalar>\n" + str(values.size) + "\n(\n" + "\n".join(f"{value:.17g}" for value in values) + "\n)\n;"
    rendered, count = _INTERNAL_FIELD.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError(f"Could not replace exactly one alpha internalField in {path}")
    if re.search(r"\bclass\s+volScalarField\s*;", rendered) is None or re.search(r"\bobject\s+alpha\s*;", rendered) is None:
        raise ValueError(f"alpha template has an unexpected OpenFOAM header: {path}")
    path.write_text(rendered, encoding="utf-8")


def _patch_allrun_to_restore_fd_alpha(path: Path) -> None:
    """Restore the cellwise FD state after the template's ``setFields`` call.

    The compiled G2 template initializes alpha with ``setFields``.  Leaving
    that untouched would overwrite the staged nonuniform FD state before the
    solver starts, yielding a numerically plausible but invalid zero direction.
    """

    if not path.is_file():
        raise FileNotFoundError(f"compiled case Allrun is missing: {path}")
    text = path.read_text(encoding="utf-8")
    marker = "runApplication setFields"
    if text.count(marker) != 1:
        raise ValueError(f"Allrun must contain exactly one {marker!r}: {path}")
    if not text.startswith("#!/"):
        raise ValueError(f"Allrun must start with a POSIX shell shebang: {path}")
    patched = text.replace(marker, marker + "\n# Restore the provenance-bound cellwise FD alpha after setFields.\ncp 0.orig/alpha 0/alpha")
    path.write_bytes(patched.encode("utf-8"))
    # Preserve/correct the executable bit for local and WSL invocation. Docker
    # also runs chmod defensively, but the staged artifact itself is usable.
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _read_final_response_coefficient(case_dir: Path, response_id: str) -> float:
    _validate_optional_run_summary(case_dir)
    root = case_dir / "optimisation" / "objective"
    if not root.is_dir():
        raise FileNotFoundError(f"OpenFOAM objective directory is missing: {root}")
    candidates = [path for path in root.glob(f"**/{response_id}*") if path.is_file() and "Instant" not in path.name]
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one final objective file for {response_id!r} under {root}; found {len(candidates)}")
    rows = [line.split() for line in candidates[0].read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not rows:
        raise ValueError(f"OpenFOAM objective file has no data rows: {candidates[0]}")
    row = rows[-1]
    index = 2 if len(row) >= 3 else 1
    try:
        value = float(row[index])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Could not parse final objective coefficient: {candidates[0]}") from exc
    if not isfinite(value):
        raise ValueError(f"OpenFOAM objective coefficient is non-finite: {candidates[0]}")
    return value


def _validate_optional_run_summary(case_dir: Path) -> None:
    """Reject an explicitly recorded failed or dry-run execution.

    A missing summary is allowed for externally injected runners, but if the
    shared ``run_openfoam_case`` execution wrapper recorded one, its status is
    an authoritative prerequisite for using the numerical response.
    """

    path = case_dir / "openfoam_run_summary.json"
    if not path.exists():
        return
    summary = _read_json(path)
    if summary.get("dry_run") is True or summary.get("ok") is not True:
        raise ValueError(f"OpenFOAM FD case did not complete successfully: {path}")


def _require_unit_interval(values: np.ndarray, name: str) -> None:
    invalid = np.flatnonzero((values < -1.0e-12) | (values > 1.0 + 1.0e-12) | ~np.isfinite(values))
    if invalid.size:
        index = int(invalid[0])
        raise ValueError(f"{name} leaves [0, 1] at source cell {index}: {values[index]:.17g}; clipping is forbidden")


def _sign_match(left: float, right: float) -> bool:
    if abs(left) <= 1.0e-12:
        return abs(right) <= 1.0e-12
    return abs(right) > 1.0e-12 and left * right > 0.0


def _finite_vector(values: object, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1 or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"{name} must be a one-dimensional numeric array")
    result = np.asarray(array, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} must contain finite values")
    return result


def _read_json(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    return raw


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError(f"{key} must be an object")
    return result


def _text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{key} must be a non-empty string")
    return result


def _finite_float(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _positive_float(value: object, name: str) -> float:
    result = _finite_float(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


__all__ = [
    "NativeG2FDDirectionArtifacts",
    "NativeG2FDDirectionValidation",
    "execute_native_g2_openfoam_fd_direction",
    "prepare_native_g2_openfoam_fd_direction",
    "validate_native_g2_openfoam_fd_direction",
]
