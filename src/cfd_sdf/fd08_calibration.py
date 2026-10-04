"""Independent raw-data analysis for Candidate C FD-08.

This module has no solver dependency.  It recomputes the registered [80, 120]
tU/L force means from raw histories, derives a Candidate-C-specific absolute
response floor from the preregistered baseline repeats, and applies the same
deterministic ladder-selection/verdict rules to calibration and formal data.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from statistics import median

import numpy as np

from cfd_sdf.fd08_contract import PLATEAU_RELATIVE_LIMIT

CALIBRATION_BASELINE_REPEATS = 5
FORMAL_EPSILON_COUNT = 5
FORMAL_DIRECTION_IDS = (
    "D0_interface_offset", "D1_filtered_seed11", "D2_filtered_seed2026",
)
MINIMUM_CALIBRATION_EPSILON_COUNT = 7
MINIMUM_CALIBRATION_SPAN_RATIO = 100.0
BASELINE_RELATIVE_FLOOR = 1e-8
FLOAT32_DIRECTION_RELATIVE_L2_ERROR_LIMIT = 0.05
FORCE_COLUMNS = (
    "step", "t_u_l", "fx_solver", "fy_solver", "fz_solver",
    "drag_solver", "downforce_solver", "pressure_fx_solver",
    "pressure_fy_solver", "pressure_fz_solver", "viscous_fx_solver",
    "viscous_fy_solver", "viscous_fz_solver",
)
RUNNER_STATE_GATES = frozenset({
    "solver_step_markers", "force_components_consistent", "host_metrics_match_summary",
    "finite", "t_end_reached", "state_identity", "body_and_backend", "vram",
})
CROSS_KERNEL_RUNTIME_FIELDS = ("julia_version", "waterlily_version", "cuda_jl_version", "gpu_name")


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _interpolate(left: Mapping[str, float], right: Mapping[str, float], t: float) -> dict[str, float]:
    dt = right["t_u_l"] - left["t_u_l"]
    if dt <= 0.0:
        raise ValueError("raw force timestamps must be strictly increasing")
    alpha = (t - left["t_u_l"]) / dt
    return {key: t if key == "t_u_l" else left[key] + alpha * (right[key] - left[key])
            for key in FORCE_COLUMNS}


def clipped_time_mean_from_rows(
    rows: Sequence[Mapping[str, float]],
    column: str,
    *,
    start_t_u_l: float = 80.0,
    end_t_u_l: float = 120.0,
) -> float:
    """Return a trapezoidal time mean with linearly interpolated exact endpoints."""
    if column not in FORCE_COLUMNS or column in {"step", "t_u_l"}:
        raise ValueError(f"unsupported force-history column: {column}")
    if len(rows) < 2 or not start_t_u_l < end_t_u_l:
        raise ValueError("a positive force window and at least two raw rows are required")
    if rows[0]["t_u_l"] > start_t_u_l or rows[-1]["t_u_l"] < end_t_u_l:
        raise ValueError("raw force history does not bracket both registered endpoints")
    times = [float(row["t_u_l"]) for row in rows]
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("raw force timestamps must be strictly increasing")

    def at(t: float) -> dict[str, float]:
        for index, row in enumerate(rows):
            if row["t_u_l"] == t:
                return dict(row)
            if row["t_u_l"] > t:
                if index == 0:
                    break
                return _interpolate(rows[index - 1], row, t)
        raise ValueError("raw force history does not bracket the requested endpoint")

    clipped = [at(start_t_u_l), *[dict(row) for row in rows
                                  if start_t_u_l < row["t_u_l"] < end_t_u_l],
               at(end_t_u_l)]
    integral = math.fsum(
        0.5 * (left[column] + right[column]) * (right["t_u_l"] - left["t_u_l"])
        for left, right in zip(clipped, clipped[1:])
    )
    return integral / (end_t_u_l - start_t_u_l)


def recompute_force_history(
    path: Path,
    *,
    force_scale_n_per_solver_force: float = 1.0 / 900.0,
    window_t_u_l: tuple[float, float] = (80.0, 120.0),
    force_component_tolerances: tuple[float, float] | None = None,
) -> dict[str, object]:
    """Hash and independently recompute drag/downforce in N from a raw CSV."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"raw force history is missing: {path}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    scale = _finite_number(force_scale_n_per_solver_force, "force scale")
    if scale <= 0.0:
        raise ValueError("force scale must be positive")
    try:
        text = raw.decode("utf-8")
        reader = csv.DictReader(text.splitlines())
        if tuple(reader.fieldnames or ()) != FORCE_COLUMNS:
            raise ValueError("raw force-history CSV schema mismatch")
        rows = [{key: _finite_number(float(row[key]), key) for key in FORCE_COLUMNS}
                for row in reader]
    except (UnicodeDecodeError, TypeError, KeyError, csv.Error) as exc:
        raise ValueError(f"invalid raw force-history CSV: {path}") from exc
    if not rows or any(right["step"] <= left["step"] for left, right in zip(rows, rows[1:])):
        raise ValueError("raw force history must contain strictly increasing solver steps")
    component_audit = None
    if force_component_tolerances is not None:
        if len(force_component_tolerances) != 2:
            raise ValueError("force-component tolerances must be (relative, absolute)")
        component_audit = verify_force_component_semantics(
            rows,
            relative_tolerance=force_component_tolerances[0],
            absolute_tolerance=force_component_tolerances[1],
        )
    start, end = map(float, window_t_u_l)
    middle = (start + end) / 2.0
    means = {
        "drag": clipped_time_mean_from_rows(rows, "drag_solver", start_t_u_l=start, end_t_u_l=end) * scale,
        "downforce": clipped_time_mean_from_rows(rows, "downforce_solver", start_t_u_l=start, end_t_u_l=end) * scale,
    }
    stationarity = {}
    for response, column in (("drag", "drag_solver"), ("downforce", "downforce_solver")):
        whole = clipped_time_mean_from_rows(rows, column, start_t_u_l=start, end_t_u_l=end)
        first = clipped_time_mean_from_rows(rows, column, start_t_u_l=start, end_t_u_l=middle)
        second = clipped_time_mean_from_rows(rows, column, start_t_u_l=middle, end_t_u_l=end)
        stationarity[response] = abs(first - second) / max(abs(whole), np.finfo(np.float64).eps)
    return {
        "path": path.as_posix(), "sha256": digest, "row_count": len(rows),
        "window_t_u_l": [start, end], "force_scale_n_per_solver_force": scale,
        "force_n": means, "force_component_audit": component_audit,
        "stationarity_relative_half_window_drift": stationarity,
    }


def verify_force_component_semantics(
    rows: Sequence[Mapping[str, float]], *, relative_tolerance: float, absolute_tolerance: float
) -> dict[str, object]:
    """Independently check force-on-body projections and pressure/viscous closure."""
    rel = _finite_number(relative_tolerance, "force component relative tolerance")
    absolute = _finite_number(absolute_tolerance, "force component absolute tolerance")
    if rel < 0.0 or absolute < 0.0 or not rows:
        raise ValueError("force component tolerances must be nonnegative and rows nonempty")
    checked = 0
    for index, row in enumerate(rows):
        consistent = (
            math.isclose(row["fx_solver"], row["drag_solver"], rel_tol=rel, abs_tol=absolute)
            and math.isclose(row["downforce_solver"], -row["fz_solver"], rel_tol=rel, abs_tol=absolute)
            and all(math.isclose(
                row[f"{axis}_solver"],
                row[f"pressure_{axis}_solver"] + row[f"viscous_{axis}_solver"],
                rel_tol=rel, abs_tol=absolute,
            ) for axis in ("fx", "fy", "fz"))
        )
        if not consistent:
            raise ValueError(f"force-on-body component/sign semantics failed at raw row {index}")
        checked += 1
    return {"verified": True, "row_count": checked,
            "relative_tolerance": rel, "absolute_tolerance": absolute,
            "semantics": "drag=+Fx; downforce=-Fz; total=pressure+viscous"}


def inspect_runner_state_gates(state: Mapping[str, object], run_id: str) -> dict[str, bool]:
    """Validate a terminal gate record while preserving registered gate failures."""
    gates = state.get("gates")
    if (state.get("status") not in {"COMPLETED", "GATE_FAILED"}
            or not isinstance(gates, dict) or set(gates) != RUNNER_STATE_GATES
            or any(value is not True and value is not False for value in gates.values())):
        raise ValueError(f"solver state has a failed/missing gate record: {run_id}")
    expected_status = "COMPLETED" if all(value is True for value in gates.values()) else "GATE_FAILED"
    if state.get("status") != expected_status:
        raise ValueError(f"solver state status does not match its registered gates: {run_id}")
    return dict(gates)


def verify_runner_state_gates(state: Mapping[str, object], run_id: str) -> dict[str, bool]:
    """Require the complete runner gate schema with every gate literally true."""
    gates = inspect_runner_state_gates(state, run_id)
    if any(value is not True for value in gates.values()):
        raise ValueError(f"solver state has a failed registered gate: {run_id}")
    return gates


def derive_response_floor(baseline_values_n: Iterable[float]) -> dict[str, float | int]:
    """Freeze a positive response floor from exactly five same-state repeats.

    The repeat span measures observed same-input variation.  The registered
    relative guard prevents an identical-repeat set from yielding a zero floor.
    The formula is applied separately to drag and downforce, in N.
    """
    values = tuple(_finite_number(value, "baseline force") for value in baseline_values_n)
    if len(values) != CALIBRATION_BASELINE_REPEATS:
        raise ValueError(f"exactly {CALIBRATION_BASELINE_REPEATS} calibration baseline repeats are required")
    center = float(median(values))
    span = max(values) - min(values)
    guard = BASELINE_RELATIVE_FLOOR * max(1.0, abs(center))
    return {
        "repeat_count": len(values), "median_n": center, "min_n": min(values),
        "max_n": max(values), "span_n": span, "relative_guard_n": guard,
        "response_floor_n": max(span, guard),
    }


def validate_calibration_ladder(epsilons_m: Iterable[float]) -> tuple[float, ...]:
    values = tuple(_finite_number(value, "calibration epsilon") for value in epsilons_m)
    if len(values) < MINIMUM_CALIBRATION_EPSILON_COUNT:
        raise ValueError(f"calibration requires at least {MINIMUM_CALIBRATION_EPSILON_COUNT} epsilon values")
    if any(value <= 0.0 for value in values) or tuple(sorted(set(values))) != values:
        raise ValueError("calibration epsilons must be unique, positive and strictly increasing")
    if values[-1] / values[0] < MINIMUM_CALIBRATION_SPAN_RATIO:
        raise ValueError(f"calibration ladder must span at least {MINIMUM_CALIBRATION_SPAN_RATIO:g}x")
    return values


def validate_formal_epsilon_ladder(epsilons_m: Iterable[float]) -> tuple[float, ...]:
    """Validate the five-point formal ladder selected from calibration."""
    values = tuple(_finite_number(value, "formal epsilon") for value in epsilons_m)
    if len(values) != FORMAL_EPSILON_COUNT:
        raise ValueError(f"formal ladder requires exactly {FORMAL_EPSILON_COUNT} epsilon values")
    if any(value <= 0.0 for value in values) or tuple(sorted(set(values))) != values:
        raise ValueError("formal epsilons must be unique, positive and strictly increasing")
    return values


def verify_output_manifest(result_root: Path, runner_result_path: Path | None = None) -> dict[str, object]:
    """Independently verify every saved runner artifact against its SHA manifest."""
    root = Path(result_root).resolve()
    manifest_path = root / "sha256.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("runner output SHA-256 manifest is missing or unsafe")
    done_path = root / "DONE"
    if not done_path.is_file() or done_path.is_symlink():
        raise ValueError("runner terminal DONE marker is missing or unsafe")
    try:
        done = json.loads(done_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("runner terminal DONE marker is invalid JSON") from exc
    if not isinstance(done, dict) or done.get("status") != "FINISHED_STATE_LOOP":
        raise ValueError("runner terminal DONE marker does not report a finished state loop")
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("runner output SHA-256 manifest is invalid JSON") from exc
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("runner output SHA-256 manifest must be a nonempty object")

    expected: dict[str, str] = {}
    for name, digest in manifest.items():
        if not isinstance(name, str) or not name or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("runner output manifest contains an unsafe relative path")
        if (name != Path(name).as_posix() or name in {"sha256.json", "DONE"}
                or not isinstance(digest, str) or len(digest) != 64):
            raise ValueError("runner output manifest contains a reserved path or invalid SHA-256")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValueError("runner output manifest contains a non-hex SHA-256") from exc
        expected[name] = digest.lower()

    actual: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"runner output contains a symbolic link: {path.relative_to(root)}")
        relative = path.relative_to(root).as_posix()
        if path.is_file() and relative not in {"sha256.json", "DONE"}:
            actual[path.relative_to(root).as_posix()] = path
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(f"runner output inventory differs from manifest; missing={missing}, extra={extra}")

    for name, path in actual.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]:
            raise ValueError(f"runner output SHA-256 mismatch: {name}")

    if runner_result_path is not None:
        terminal = Path(runner_result_path).resolve()
        if root not in terminal.parents:
            raise ValueError("runner terminal must be inside the manifested output directory")
        name = terminal.relative_to(root).as_posix()
        if expected.get(name) != hashlib.sha256(terminal.read_bytes()).hexdigest():
            raise ValueError("runner terminal is not bound by the verified output manifest")
    return {
        "manifest_path": manifest_path.as_posix(),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "terminal_marker_path": done_path.as_posix(),
        "terminal_marker_sha256": hashlib.sha256(done_path.read_bytes()).hexdigest(),
        "terminal_status_counts": done.get("status_counts"),
        "verified_file_count": len(expected),
        "inventory_sha256": hashlib.sha256(
            "\n".join(f"{name}  {expected[name]}" for name in sorted(expected)).encode()
        ).hexdigest(),
    }


def verify_runtime_artifacts(result_root: Path, backend: Mapping[str, object]) -> dict[str, object]:
    """Independently verify the runner's pinned T4 smoke and observed GPU inventory."""
    root = Path(result_root).resolve()
    inventory_path = root / "nvidia_smi.csv"
    smoke_path = root / "julia_smoke.log"
    if not inventory_path.is_file() or inventory_path.is_symlink() or not smoke_path.is_file() or smoke_path.is_symlink():
        raise ValueError("Kaggle runtime inventory or Julia smoke log is missing or unsafe")
    try:
        with inventory_path.open(newline="") as handle:
            rows = [[cell.strip() for cell in row] for row in csv.reader(handle) if row]
    except (OSError, csv.Error) as exc:
        raise ValueError("Kaggle nvidia-smi inventory is invalid") from exc
    expected_count = backend.get("gpu_count")
    if (isinstance(expected_count, bool) or not isinstance(expected_count, int)
            or expected_count <= 0 or len(rows) != expected_count
            or any(len(row) != 5 for row in rows)):
        raise ValueError("Kaggle GPU inventory does not match the registered device count/schema")
    if ([row[0] for row in rows] != [str(index) for index in range(expected_count)]
            or len({row[2] for row in rows}) != expected_count
            or any(not row[2].startswith("GPU-") for row in rows)
            or any(str(backend.get("gpu_name", "")) not in row[1] for row in rows)
            or len({row[4] for row in rows}) != 1):
        raise ValueError("observed Kaggle GPU inventory differs from the registered T4 backend")
    smoke = smoke_path.read_text(errors="replace")
    markers = (
        "W0B_SMOKE_DONE", "CUDA_FUNCTIONAL true",
        f"GPU_COMPUTE_CAPABILITY {backend.get('compute_capability')}",
        f"CUDA_DRIVER_VERSION {backend.get('cuda_driver_api_version')}",
        f"CUDA_RUNTIME_VERSION {backend.get('cuda_runtime_version')}",
        f"JULIA_VERSION {backend.get('julia_version')}",
        f"CUDA_JL_VERSION {backend.get('cuda_jl_version')}",
        f"WATERLILY_VERSION {backend.get('waterlily_version')}",
        f"GPU_NAME {backend.get('gpu_name')}", "NO_SOLVER_STEP",
    )
    if any(marker not in smoke for marker in markers):
        raise ValueError("observed Kaggle runtime does not match the registered T4 smoke contract")
    return {
        "gpu_inventory_path": inventory_path.relative_to(root).as_posix(),
        "gpu_inventory_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        "gpu_rows": rows,
        "selected_gpu_uuid": rows[0][2],
        "driver_version_recorded_not_gated": rows[0][4],
        "julia_smoke_path": smoke_path.relative_to(root).as_posix(),
        "julia_smoke_sha256": hashlib.sha256(smoke_path.read_bytes()).hexdigest(),
        "pinned_smoke_markers": list(markers),
        "gpu_uuid_policy": "recorded_for_each_kernel; physical T4 UUID is not a cross-kernel equality gate",
    }


def verify_cross_kernel_runtime(actual: Mapping[str, object], reference: Mapping[str, object]) -> tuple[str, ...]:
    """Compare the qualified software/GPU model while recording per-kernel UUID and driver."""
    for field in CROSS_KERNEL_RUNTIME_FIELDS:
        if actual.get(field) != reference.get(field):
            raise ValueError(f"cross-kernel runtime differs from calibration identity: {field}")
    return CROSS_KERNEL_RUNTIME_FIELDS


def verify_source_inputs(source_inputs: Mapping[str, object], *, root: Path) -> dict[str, str]:
    """Verify every criteria-bound repository source file without following symlinks."""
    if not isinstance(source_inputs, Mapping) or not source_inputs:
        raise ValueError("criteria source input inventory is missing")
    source_root = Path(root).resolve()
    verified: dict[str, str] = {}
    for name, entry in source_inputs.items():
        if not isinstance(name, str) or not isinstance(entry, Mapping):
            raise ValueError("criteria source input entry is invalid")
        relative, expected = entry.get("path"), entry.get("sha256")
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
                or ".." in Path(relative).parts or relative != Path(relative).as_posix()
                or entry.get("location") != "source_repo"
                or not isinstance(expected, str) or len(expected) != 64):
            raise ValueError(f"criteria source input binding is invalid: {name}")
        try:
            int(expected, 16)
        except ValueError as exc:
            raise ValueError(f"criteria source input SHA-256 is not hexadecimal: {name}") from exc
        candidate = source_root / relative
        current = source_root
        for component in Path(relative).parts:
            current = current / component
            if current.is_symlink():
                raise ValueError(f"criteria source input uses a symlink: {name}")
        path = candidate.resolve()
        if source_root not in path.parents or not path.is_file():
            raise ValueError(f"criteria source input is missing or unsafe: {name}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"criteria source input SHA-256 mismatch: {name}")
        verified[name] = actual
    return verified


def verify_registered_dataset(
    criteria: Mapping[str, object], criteria_sha256: str, dataset_dir: Path
) -> dict[str, object]:
    """Check the complete locally staged immutable dataset before host analysis."""
    root = Path(dataset_dir).resolve()
    files = criteria.get("dataset_files")
    if not isinstance(files, dict) or not files:
        raise ValueError("registered dataset file inventory is missing")
    expected = dict(files)
    reserved = {"xfidc_criteria.json", "xfidc_criteria.json.sha256", "dataset-metadata.json"}
    for name, digest in expected.items():
        if (not isinstance(name, str) or not name or name != Path(name).as_posix()
                or Path(name).is_absolute() or ".." in Path(name).parts or name in reserved
                or not isinstance(digest, str) or len(digest) != 64):
            raise ValueError("registered dataset inventory contains an unsafe or invalid entry")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValueError("registered dataset inventory contains a non-hex SHA-256") from exc
    expected["xfidc_criteria.json"] = criteria_sha256
    expected["xfidc_criteria.json.sha256"] = hashlib.sha256(
        (root / "xfidc_criteria.json.sha256").read_bytes()
    ).hexdigest() if (root / "xfidc_criteria.json.sha256").is_file() else ""
    actual = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"registered dataset contains a symbolic link: {path.relative_to(root)}")
        if path.is_file() and path.relative_to(root).as_posix() != "dataset-metadata.json":
            actual[path.relative_to(root).as_posix()] = path
    if set(actual) != set(expected):
        raise ValueError("registered dataset inventory differs from its immutable criteria")
    sidecar_value = (root / "xfidc_criteria.json.sha256").read_text().strip()
    if sidecar_value != criteria_sha256:
        raise ValueError("staged dataset criteria SHA-256 sidecar mismatch")
    for name, expected_sha in files.items():
        if not isinstance(name, str) or not isinstance(expected_sha, str):
            raise ValueError("registered dataset inventory contains invalid entries")
        path = actual[name]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
            raise ValueError(f"registered dataset file SHA-256 mismatch: {name}")
    if hashlib.sha256(actual["xfidc_criteria.json"].read_bytes()).hexdigest() != criteria_sha256:
        raise ValueError("staged dataset criteria SHA-256 mismatch")
    return {
        "dataset_root": root.as_posix(),
        "verified_file_count": len(files),
        "criteria_sha256": criteria_sha256,
        "inventory_sha256": hashlib.sha256(
            "\n".join(f"{name}  {files[name]}" for name in sorted(files)).encode()
        ).hexdigest(),
    }


def audit_float32_centered_pair(
    canonical_phi: np.ndarray,
    direction: np.ndarray,
    *,
    epsilon_m: float,
    phi_plus: np.ndarray,
    phi_minus: np.ndarray,
    max_relative_l2_error: float = FLOAT32_DIRECTION_RELATIVE_L2_ERROR_LIMIT,
) -> dict[str, object]:
    """Audit the direction actually represented by a stored Float32 +/- pair."""
    epsilon = _finite_number(epsilon_m, "epsilon_m")
    limit = _finite_number(max_relative_l2_error, "Float32 direction error limit")
    if epsilon <= 0.0 or limit < 0.0:
        raise ValueError("epsilon must be positive and direction error limit nonnegative")
    base = np.asarray(canonical_phi)
    plus = np.asarray(phi_plus)
    minus = np.asarray(phi_minus)
    vector = np.asarray(direction, dtype=np.float64)
    if base.dtype != np.float32 or plus.dtype != np.float32 or minus.dtype != np.float32:
        raise ValueError("canonical and perturbed phi arrays must be Float32")
    if base.shape != plus.shape or base.shape != minus.shape or base.shape != vector.shape:
        raise ValueError("canonical phi, direction and signed perturbations must have identical shapes")
    if not all(np.isfinite(a).all() for a in (base, plus, minus, vector)):
        raise ValueError("perturbation arrays must be finite")
    expected_plus = np.asarray(base.astype(np.float64) + epsilon * vector, dtype=np.float32)
    expected_minus = np.asarray(base.astype(np.float64) - epsilon * vector, dtype=np.float32)
    if not np.array_equal(plus, expected_plus) or not np.array_equal(minus, expected_minus):
        raise ValueError("stored Float32 pair differs from the registered deterministic perturbation")
    support = vector != 0.0
    requested = vector[support]
    effective = (plus.astype(np.float64)[support] - minus.astype(np.float64)[support]) / (2.0 * epsilon)
    requested_norm = float(np.linalg.norm(requested))
    effective_norm = float(np.linalg.norm(effective))
    if requested_norm == 0.0 or effective_norm == 0.0:
        raise ValueError("Float32 pair has no nonzero effective direction on the registered support")
    relative_error = float(np.linalg.norm(effective - requested) / requested_norm)
    cosine = float(np.dot(effective, requested) / (effective_norm * requested_norm))
    changed_plus = int(np.count_nonzero(plus != base))
    changed_minus = int(np.count_nonzero(minus != base))
    if changed_plus == 0 or changed_minus == 0:
        raise ValueError("one signed perturbation rounded away in Float32 phi storage")
    if relative_error > limit:
        raise ValueError(
            f"Float32 effective direction relative L2 error {relative_error:.8g} exceeds {limit:.8g}"
        )
    return {
        "changed_node_count_plus": changed_plus,
        "changed_node_count_minus": changed_minus,
        "effective_direction_cosine": cosine,
        "effective_direction_relative_l2_error": relative_error,
        "relative_l2_error_limit": limit,
        "direction_gate_passed": True,
    }


def centered_pair(response_plus_n: float, response_minus_n: float, epsilon_m: float) -> dict[str, float | int]:
    plus = _finite_number(response_plus_n, "plus response")
    minus = _finite_number(response_minus_n, "minus response")
    epsilon = _finite_number(epsilon_m, "epsilon_m")
    if epsilon <= 0.0:
        raise ValueError("epsilon_m must be positive")
    signal = (plus - minus) / 2.0
    return {
        "response_plus_n": plus, "response_minus_n": minus,
        "centered_response_n": signal, "centered_slope_n_per_m": signal / epsilon,
        "sign": 1 if signal > 0.0 else -1 if signal < 0.0 else 0,
    }


def _plateau_metrics(rows: Sequence[Mapping[str, object]], floor_n: float) -> dict[str, object]:
    slopes = [float(row["centered_slope_n_per_m"]) for row in rows]
    reference = float(median(slopes))
    smallest_epsilon = min(float(row["epsilon_m"]) for row in rows)
    noise_equivalent = floor_n / smallest_epsilon
    normalizer = max(abs(reference), noise_equivalent)
    deviations = [abs(slope - reference) / normalizer for slope in slopes]
    signs = [int(row["sign"]) for row in rows]
    return {
        "reference_slope_n_per_m": reference,
        "directional_noise_equivalent_n_per_m": noise_equivalent,
        "relative_deviations": deviations,
        "max_relative_deviation": max(deviations),
        "signs": signs,
        "sign_consistent": bool(signs) and signs[0] != 0 and len(set(signs)) == 1,
        "plateau_pass": max(deviations) <= PLATEAU_RELATIVE_LIMIT
        and bool(signs) and signs[0] != 0 and len(set(signs)) == 1,
    }


def select_formal_epsilon_ladder(
    *,
    epsilons_m: Iterable[float],
    pairs: Mapping[str, Mapping[str, Sequence[Mapping[str, object]]]],
    response_floors_n: Mapping[str, float],
) -> dict[str, object]:
    """Select the smallest common contiguous five-epsilon window passing all six gates."""
    epsilons = validate_calibration_ladder(epsilons_m)
    expected_directions = set(pairs)
    if len(expected_directions) != 3:
        raise ValueError("calibration must contain exactly three registered directions")
    if set(response_floors_n) != {"drag", "downforce"}:
        raise ValueError("calibration requires separate drag and downforce response floors")
    lookup: dict[tuple[str, str, float], dict[str, object]] = {}
    for direction, responses in pairs.items():
        if set(responses) != {"drag", "downforce"}:
            raise ValueError(f"{direction}: both primitive responses are required")
        for response, rows in responses.items():
            by_epsilon = {float(row["epsilon_m"]): dict(row) for row in rows}
            if set(by_epsilon) != set(epsilons) or len(by_epsilon) != len(rows):
                raise ValueError(f"{direction}/{response}: calibration coverage must match the full epsilon ladder")
            floor = _finite_number(response_floors_n[response], f"{response} floor")
            if floor <= 0.0:
                raise ValueError("response floors must be positive")
            for epsilon in epsilons:
                row = by_epsilon[epsilon]
                row["resolved"] = abs(float(row["centered_response_n"])) > floor
                lookup[(direction, response, epsilon)] = row

    candidates: list[tuple[float, ...]] = []
    for start in range(len(epsilons) - FORMAL_EPSILON_COUNT + 1):
        window = epsilons[start:start + FORMAL_EPSILON_COUNT]
        passed_all = True
        for direction in sorted(expected_directions):
            for response in ("drag", "downforce"):
                rows = [lookup[(direction, response, epsilon)] for epsilon in window]
                if not all(row["resolved"] for row in rows):
                    passed_all = False
                    break
                metrics = _plateau_metrics(rows, float(response_floors_n[response]))
                if not metrics["plateau_pass"]:
                    passed_all = False
                    break
            if not passed_all:
                break
        if passed_all:
            candidates.append(window)
    selected = candidates[0] if candidates else None
    return {
        "status": "COMMON_PLATEAU_FOUND" if selected else "NO_COMMON_PLATEAU",
        "calibration_epsilon_ladder_m": list(epsilons),
        "candidate_window_count": len(candidates),
        "selected_formal_epsilon_ladder_m": list(selected) if selected else None,
        "selection_rule": "first (smallest-epsilon) contiguous five-point window for which all 3 directions x 2 responses are above their independent floors and pass the registered 5% median-slope plateau and sign gates",
        "registration_allowed": selected is not None,
    }


def classify_calibration_screen(
    *, epsilons_m: Iterable[float],
    pairs: Mapping[str, Mapping[str, Sequence[Mapping[str, object]]]],
    response_floors_n: Mapping[str, float],
    selection: Mapping[str, object],
) -> dict[str, object]:
    """Classify a failed selector without masking any resolved five-point failure."""
    epsilons = validate_calibration_ladder(epsilons_m)
    if selection.get("registration_allowed") is True:
        return {
            "verdict": "PASS",
            "resolved_failure_windows": [],
            "formal_registration_allowed": True,
            "rule": "a deterministic common five-point plateau was selected for all six series",
        }

    failures = []
    for start in range(len(epsilons) - FORMAL_EPSILON_COUNT + 1):
        window = epsilons[start:start + FORMAL_EPSILON_COUNT]
        for direction in sorted(pairs):
            for response in ("drag", "downforce"):
                rows_by_epsilon = {
                    float(row["epsilon_m"]): row
                    for row in pairs[direction][response]
                }
                rows = [rows_by_epsilon[epsilon] for epsilon in window]
                outcome = evaluate_formal_direction_response(
                    rows, response_floor_n=float(response_floors_n[response]),
                )
                if outcome["verdict"] == "FAIL":
                    failures.append({
                        "epsilon_window_m": list(window),
                        "direction_id": direction,
                        "response": response,
                        "failure_gates": outcome["failure_gates"],
                        "resolved_epsilon_m": outcome["resolved_epsilon_m"],
                    })
    verdict = "FAIL" if failures else "UNRESOLVED"
    return {
        "verdict": verdict,
        "resolved_failure_windows": failures,
        "formal_registration_allowed": False,
        "rule": (
            "when no common plateau exists, FAIL takes precedence if any contiguous five-point "
            "window has a resolved sign or plateau failure; otherwise UNRESOLVED"
        ),
    }


def evaluate_formal_direction_response(
    rows: Iterable[Mapping[str, object]], *, response_floor_n: float
) -> dict[str, object]:
    """Evaluate one formal direction/response without masking a resolved failure."""
    floor = _finite_number(response_floor_n, "response floor")
    if floor <= 0.0:
        raise ValueError("response floor must be positive")
    observations = tuple(dict(row) for row in rows)
    epsilons = [float(row["epsilon_m"]) for row in observations]
    if (len(observations) != FORMAL_EPSILON_COUNT or len(set(epsilons)) != len(epsilons)
            or any(epsilon <= 0.0 for epsilon in epsilons)):
        raise ValueError("formal direction/response requires the complete five-epsilon inventory")
    for row in observations:
        pair = centered_pair(row["response_plus_n"], row["response_minus_n"], row["epsilon_m"])
        row.update(pair)
        row["resolved"] = abs(float(pair["centered_response_n"])) > floor
    resolved = [row for row in observations if row["resolved"]]
    failures: list[str] = []
    observed_signs = {int(row["sign"]) for row in resolved}
    if 0 in observed_signs or len(observed_signs) > 1:
        failures.append("resolved_sign_inconsistency")
    plateau = _plateau_metrics(resolved, floor) if len(resolved) >= 3 else None
    if plateau is not None and not plateau["plateau_pass"]:
        failures.append("resolved_plateau_failure")
    if failures:
        verdict = "FAIL"
    elif len(resolved) < 3 or len(resolved) != len(observations):
        verdict = "UNRESOLVED"
    elif plateau is None:
        verdict = "UNRESOLVED"
    else:
        verdict = "PASS"
    return {
        "verdict": verdict, "response_floor_n": floor,
        "resolved_epsilon_m": sorted(float(row["epsilon_m"]) for row in resolved),
        "unresolved_epsilon_m": sorted(float(row["epsilon_m"]) for row in observations if not row["resolved"]),
        "resolved_count": len(resolved), "required_plateau_count": 3,
        "plateau": plateau, "failure_gates": failures,
        "epsilon_rows": sorted(observations, key=lambda row: float(row["epsilon_m"])),
    }


def aggregate_formal_verdict(
    results: Mapping[str, Mapping[str, object]],
    *, integrity_failures: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Combine the six response verdicts and preserve formal-integrity FAIL precedence."""
    expected = {f"{direction}/{response}" for direction in FORMAL_DIRECTION_IDS
                for response in ("drag", "downforce")}
    if set(results) != expected:
        raise ValueError(f"formal verdict requires exactly the six registered combinations: {sorted(expected)}")
    verdicts = [results[key].get("verdict") for key in sorted(expected)]
    if any(value not in {"PASS", "FAIL", "UNRESOLVED"} for value in verdicts):
        raise ValueError("each formal combination requires PASS, FAIL, or UNRESOLVED")
    integrity = tuple(integrity_failures)
    if any(not isinstance(item, Mapping) or not item for item in integrity):
        raise ValueError("formal integrity failures must be nonempty records")
    overall = (
        "FAIL" if "FAIL" in verdicts or integrity
        else "UNRESOLVED" if "UNRESOLVED" in verdicts
        else "PASS"
    )
    return {"verdict": overall, "combination_verdicts": dict(results),
            "pass_count": verdicts.count("PASS"), "fail_count": verdicts.count("FAIL"),
            "unresolved_count": verdicts.count("UNRESOLVED"),
            "integrity_failure_count": len(integrity),
            "qualification_flags": {key: False for key in (
                "shape_update_allowed", "fd_oracle", "field_gradient", "reverse", "optimizer", "topology")}}


__all__ = [
    "BASELINE_RELATIVE_FLOOR", "CALIBRATION_BASELINE_REPEATS",
    "FLOAT32_DIRECTION_RELATIVE_L2_ERROR_LIMIT", "FORMAL_DIRECTION_IDS",
    "aggregate_formal_verdict",
    "audit_float32_centered_pair", "centered_pair", "clipped_time_mean_from_rows",
    "classify_calibration_screen", "derive_response_floor", "evaluate_formal_direction_response",
    "recompute_force_history", "select_formal_epsilon_ladder",
    "validate_calibration_ladder", "validate_formal_epsilon_ladder",
    "verify_force_component_semantics", "verify_output_manifest", "verify_registered_dataset",
    "verify_cross_kernel_runtime", "inspect_runner_state_gates", "verify_runner_state_gates", "verify_runtime_artifacts",
    "verify_source_inputs",
]
